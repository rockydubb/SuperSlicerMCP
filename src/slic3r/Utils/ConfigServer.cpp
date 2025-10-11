#include "ConfigServer.hpp"
#include "../GUI/GUI_App.hpp"
#include "../GUI/Plater.hpp"
#include "../GUI/MainFrame.hpp"
#include "../GUI/Tab.hpp"
#include "libslic3r/PresetBundle.hpp"
#include "libslic3r/PrintConfig.hpp"
#include "libslic3r/Model.hpp"
#include "libslic3r/Print.hpp"

#include <wx/arrstr.h>
#include <wx/string.h>
#include <boost/asio.hpp>
#include <boost/beast.hpp>
#include <boost/beast/http.hpp>
#include <boost/log/trivial.hpp>
#include <boost/algorithm/string.hpp>
#include <sstream>
#include <regex>
#include <set>
#include <map>

namespace Slic3r {

namespace beast = boost::beast;
namespace http = beast::http;
namespace net = boost::asio;
using tcp = net::ip::tcp;

ConfigServer::ConfigServer()
    : m_io_context(std::make_unique<boost::asio::io_context>())
{
}

ConfigServer::~ConfigServer()
{
    stop();
}

bool ConfigServer::start(uint16_t port)
{
    if (m_running) {
        return false;
    }
    
    try {
        m_port = port;
        m_acceptor = std::make_unique<tcp::acceptor>(*m_io_context, tcp::endpoint(tcp::v4(), port));
        m_acceptor->set_option(boost::asio::socket_base::reuse_address(true));
        
        m_running = true;
        m_server_thread = std::make_unique<std::thread>(&ConfigServer::run_server, this);
        
        BOOST_LOG_TRIVIAL(info) << "ConfigServer started on port " << port;
        return true;
    }
    catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(error) << "Failed to start ConfigServer: " << e.what();
        m_running = false;
        return false;
    }
}

void ConfigServer::stop()
{
    if (!m_running) {
        return;
    }
    
    m_running = false;
    
    if (m_acceptor) {
        m_acceptor->close();
    }
    
    m_io_context->stop();
    
    if (m_server_thread && m_server_thread->joinable()) {
        m_server_thread->join();
    }
    
    BOOST_LOG_TRIVIAL(info) << "ConfigServer stopped";
}

void ConfigServer::run_server()
{
    while (m_running) {
        try {
            auto socket = std::make_shared<tcp::socket>(*m_io_context);
            m_acceptor->accept(*socket);
            
            if (!m_running) {
                break;
            }
            
            // Handle client in a separate thread
            std::thread client_thread(&ConfigServer::handle_client, this, socket);
            client_thread.detach();
        }
        catch (const std::exception& e) {
            if (m_running) {
                BOOST_LOG_TRIVIAL(error) << "ConfigServer accept error: " << e.what();
            }
        }
    }
}

void ConfigServer::handle_client(std::shared_ptr<tcp::socket> socket)
{
    try {
        beast::flat_buffer buffer;
        http::request<http::string_body> request;
        boost::system::error_code ec;
        
        // Read the HTTP request
        http::read(*socket, buffer, request, ec);
        
        if (!ec) {
            // Create HTTP response
            http::response<http::string_body> response;
            response.version(request.version());
            response.keep_alive(false);
            
            // Handle different endpoints
            if (request.method() == http::verb::post && request.target() == "/api/command") {
                // Process JSON command from body
                std::string json_response = process_command(request.body());
                response.result(http::status::ok);
                response.set(http::field::content_type, "application/json");
                response.body() = json_response;
            }
            else if (request.method() == http::verb::get && request.target() == "/api/status") {
                // Direct status endpoint
                response.result(http::status::ok);
                response.set(http::field::content_type, "application/json");
                response.body() = handle_get_status("");
            }
            else if (request.method() == http::verb::get && request.target() == "/api/presets") {
                // Direct presets endpoint
                response.result(http::status::ok);
                response.set(http::field::content_type, "application/json");
                response.body() = handle_list_presets("");
            }
            else if (request.method() == http::verb::get && request.target().starts_with("/api/config/")) {
                // Get config value: GET /api/config/{key}
                std::string key(request.target().substr(12)); // Remove "/api/config/"
                std::string params = "{\"key\": \"" + key + "\"}";
                response.result(http::status::ok);
                response.set(http::field::content_type, "application/json");
                response.body() = handle_get_config(params);
            }
            else if (request.method() == http::verb::put && request.target().starts_with("/api/config/")) {
                // Set config value: PUT /api/config/{key} with body containing the value
                std::string key(request.target().substr(12)); // Remove "/api/config/"
                std::string params = "{\"key\": \"" + key + "\", \"value\": \"" + request.body() + "\"}";
                response.result(http::status::ok);
                response.set(http::field::content_type, "application/json");
                response.body() = handle_set_config(params);
            }
            else if (request.method() == http::verb::get && request.target() == "/api/config") {
                // List all available config keys
                response.result(http::status::ok);
                response.set(http::field::content_type, "application/json");
                response.body() = handle_list_config_keys();
            }
            else {
                response.result(http::status::not_found);
                response.set(http::field::content_type, "application/json");
                response.body() = "{\"error\": \"Endpoint not found\"}";
            }
            
            // Add CORS headers for browser access
            response.set(http::field::access_control_allow_origin, "*");
            response.set(http::field::access_control_allow_methods, "GET, POST, OPTIONS");
            response.set(http::field::access_control_allow_headers, "Content-Type");
            
            // Prepare the response
            response.prepare_payload();
            
            // Send the response
            http::write(*socket, response, ec);
        }
    }
    catch (const std::exception& e) {
        BOOST_LOG_TRIVIAL(error) << "ConfigServer client error: " << e.what();
    }
    
    socket->shutdown(tcp::socket::shutdown_send);
    socket->close();
}

std::string ConfigServer::process_command(const std::string& json_request)
{
    // Simple JSON parsing - extract command and params
    // Expected format: {"command": "get_config", "params": {"key": "layer_height"}}
    
    std::regex cmd_regex("\"command\"\\s*:\\s*\"([^\"]+)\"");
    std::regex params_regex("\"params\"\\s*:\\s*\\{([^}]*)\\}");
    
    std::smatch cmd_match;
    std::smatch params_match;
    
    std::string command;
    std::string params;
    
    if (std::regex_search(json_request, cmd_match, cmd_regex)) {
        command = cmd_match[1];
    }
    
    if (std::regex_search(json_request, params_match, params_regex)) {
        params = params_match[1];
    }
    
    // Route to appropriate handler
    try {
        if (command == "get_config") {
            return handle_get_config(params);
        } else if (command == "set_config") {
            return handle_set_config(params);
        } else if (command == "get_preset") {
            return handle_get_preset(params);
        } else if (command == "list_presets") {
            return handle_list_presets(params);
        } else if (command == "slice") {
            return handle_slice(params);
        } else if (command == "export") {
            return handle_export(params);
        } else if (command == "get_status") {
            return handle_get_status(params);
        } else if (command == "load_file") {
            return handle_load_file(params);
        } else {
            // Check custom handlers
            auto it = m_command_handlers.find(command);
            if (it != m_command_handlers.end()) {
                return it->second(command, params);
            }
            return "{\"error\": \"Unknown command: " + command + "\"}";
        }
    }
    catch (const std::exception& e) {
        return "{\"error\": \"" + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_get_config(const std::string& params)
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    // Extract key from params
    std::regex key_regex("\"key\"\\s*:\\s*\"([^\"]+)\"");
    std::smatch key_match;
    
    if (!std::regex_search(params, key_match, key_regex)) {
        return "{\"error\": \"Missing key parameter\"}";
    }
    
    std::string key = key_match[1];
    
    try {
        // Get the preset bundle
        const PresetBundle* preset_bundle = GUI::wxGetApp().preset_bundle.get();
        if (!preset_bundle) {
            return "{\"error\": \"Preset bundle not available\"}";
        }
        
        // Try to find the config option in different configs
        const ConfigOption* opt = nullptr;
        std::string preset_type;
        
        // Check print config
        if (!opt) {
            const DynamicPrintConfig& config = preset_bundle->fff_prints.get_edited_preset().config;
            opt = config.option(key);
            if (opt) preset_type = "print";
        }
        
        // Check filament config
        if (!opt) {
            const DynamicPrintConfig& config = preset_bundle->filaments.get_edited_preset().config;
            opt = config.option(key);
            if (opt) preset_type = "filament";
        }
        
        // Check printer config
        if (!opt) {
            const DynamicPrintConfig& config = preset_bundle->printers.get_edited_preset().config;
            opt = config.option(key);
            if (opt) preset_type = "printer";
        }
        
        if (!opt) {
            return "{\"error\": \"Config option not found: " + key + "\"}";
        }
        
        // Serialize the value
        std::string value = opt->serialize();
        
        // Get the config definition for tooltip and other metadata
        std::string tooltip;
        std::string label;
        std::string sidetext;
        const ConfigOptionDef* def = print_config_def.get(key);
        if (def) {
            tooltip = def->tooltip;
            label = def->label;
            sidetext = def->sidetext;
            
            // Escape quotes in tooltip for JSON
            size_t pos = 0;
            while ((pos = tooltip.find('"', pos)) != std::string::npos) {
                tooltip.replace(pos, 1, "\\\"");
                pos += 2;
            }
            // Escape newlines
            pos = 0;
            while ((pos = tooltip.find('\n', pos)) != std::string::npos) {
                tooltip.replace(pos, 1, "\\n");
                pos += 2;
            }
        }
        
        // Build response
        std::stringstream response;
        response << "{";
        response << "\"key\": \"" << key << "\", ";
        response << "\"value\": \"" << value << "\", ";
        response << "\"type\": \"" << preset_type << "\"";
        if (!tooltip.empty()) {
            response << ", \"tooltip\": \"" << tooltip << "\"";
        }
        if (!label.empty()) {
            response << ", \"label\": \"" << label << "\"";
        }
        if (!sidetext.empty()) {
            response << ", \"unit\": \"" << sidetext << "\"";
        }
        response << "}";
        
        return response.str();
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to get config: " + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_set_config(const std::string& params)
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    // Extract key and value from params
    std::regex key_regex("\"key\"\\s*:\\s*\"([^\"]+)\"");
    std::regex value_regex("\"value\"\\s*:\\s*\"([^\"]+)\"");
    std::smatch key_match, value_match;
    
    if (!std::regex_search(params, key_match, key_regex)) {
        return "{\"error\": \"Missing key parameter\"}";
    }
    if (!std::regex_search(params, value_match, value_regex)) {
        return "{\"error\": \"Missing value parameter\"}";
    }
    
    std::string key = key_match[1];
    std::string value = value_match[1];
    
    try {
        // Get the plater and tab
        GUI::Plater* plater = GUI::wxGetApp().plater();
        if (!plater) {
            return "{\"error\": \"Plater not available\"}";
        }
        
        // This needs to be done in the GUI thread
        GUI::wxGetApp().CallAfter([this, key, value]() {
            try {
                // Get the appropriate tab and update the config
                PresetBundle* preset_bundle = GUI::wxGetApp().preset_bundle.get();
                
                // Find which config contains this key
                DynamicPrintConfig* target_config = nullptr;
                GUI::Tab* target_tab = nullptr;
                
                // Check print config
                if (preset_bundle->fff_prints.get_edited_preset().config.has(key)) {
                    target_config = &preset_bundle->fff_prints.get_edited_preset().config;
                    target_tab = GUI::wxGetApp().get_tab(Preset::TYPE_FFF_PRINT);
                }
                // Check filament config
                else if (preset_bundle->filaments.get_edited_preset().config.has(key)) {
                    target_config = &preset_bundle->filaments.get_edited_preset().config;
                    target_tab = GUI::wxGetApp().get_tab(Preset::TYPE_FFF_FILAMENT);
                }
                // Check printer config
                else if (preset_bundle->printers.get_edited_preset().config.has(key)) {
                    target_config = &preset_bundle->printers.get_edited_preset().config;
                    target_tab = GUI::wxGetApp().get_tab(Preset::TYPE_PRINTER);
                }
                
                if (target_config && target_tab) {
                    // Update the config value
                    target_config->set_deserialize_strict(key, value);
                    
                    // Mark as modified and update UI
                    target_tab->update_dirty();
                    target_tab->reload_config();
                    
                    // Trigger config update callback if set
                    if (m_config_update_callback) {
                        m_config_update_callback(key, value);
                    }
                }
            }
            catch (const std::exception& e) {
                BOOST_LOG_TRIVIAL(error) << "Failed to set config: " << e.what();
            }
        });
        
        return "{\"success\": true, \"key\": \"" + key + "\", \"value\": \"" + value + "\"}";
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to set config: " + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_get_preset(const std::string& params)
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    // Extract preset type from params
    std::regex type_regex("\"type\"\\s*:\\s*\"([^\"]+)\"");
    std::smatch type_match;
    
    std::string preset_type = "print"; // default
    if (std::regex_search(params, type_match, type_regex)) {
        preset_type = type_match[1];
    }
    
    try {
        const PresetBundle* preset_bundle = GUI::wxGetApp().preset_bundle.get();
        const Preset* preset = nullptr;
        
        if (preset_type == "print") {
            preset = &preset_bundle->fff_prints.get_edited_preset();
        } else if (preset_type == "filament") {
            preset = &preset_bundle->filaments.get_edited_preset();
        } else if (preset_type == "printer") {
            preset = &preset_bundle->printers.get_edited_preset();
        }
        
        if (!preset) {
            return "{\"error\": \"Invalid preset type: " + preset_type + "\"}";
        }
        
        std::stringstream response;
        response << "{";
        response << "\"name\": \"" << preset->name << "\", ";
        response << "\"type\": \"" << preset_type << "\", ";
        response << "\"is_dirty\": " << (preset->is_dirty ? "true" : "false") << ", ";
        response << "\"is_system\": " << (preset->is_system ? "true" : "false");
        response << "}";
        
        return response.str();
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to get preset: " + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_list_presets(const std::string& params)
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    try {
        const PresetBundle* preset_bundle = GUI::wxGetApp().preset_bundle.get();
        
        std::stringstream response;
        response << "{\"presets\": [";
        
        bool first = true;
        
        // Add print presets
        for (std::size_t i = 0; i < preset_bundle->fff_prints.size(); ++i) {
            const Preset& preset = preset_bundle->fff_prints.get_presets()[i];
            if (preset.is_visible && !preset.is_default) {
                if (!first) response << ", ";
                response << "{\"name\": \"" << preset.name << "\", \"type\": \"print\"}";
                first = false;
            }
        }
        
        // Add filament presets
        for (std::size_t i = 0; i < preset_bundle->filaments.size(); ++i) {
            const Preset& preset = preset_bundle->filaments.get_presets()[i];
            if (preset.is_visible && !preset.is_default) {
                if (!first) response << ", ";
                response << "{\"name\": \"" << preset.name << "\", \"type\": \"filament\"}";
                first = false;
            }
        }
        
        // Add printer presets
        for (std::size_t i = 0; i < preset_bundle->printers.size(); ++i) {
            const Preset& preset = preset_bundle->printers.get_presets()[i];
            if (preset.is_visible && !preset.is_default) {
                if (!first) response << ", ";
                response << "{\"name\": \"" << preset.name << "\", \"type\": \"printer\"}";
                first = false;
            }
        }
        
        response << "]}";
        
        return response.str();
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to list presets: " + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_slice(const std::string& params)
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    try {
        GUI::Plater* plater = GUI::wxGetApp().plater();
        if (!plater) {
            return "{\"error\": \"Plater not available\"}";
        }
        
        // Trigger slicing in GUI thread
        GUI::wxGetApp().CallAfter([plater]() {
            plater->reslice();
        });
        
        return "{\"success\": true, \"message\": \"Slicing started\"}";
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to start slicing: " + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_export(const std::string& params)
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    // Extract path from params
    std::regex path_regex("\"path\"\\s*:\\s*\"([^\"]+)\"");
    std::smatch path_match;
    
    if (!std::regex_search(params, path_match, path_regex)) {
        return "{\"error\": \"Missing path parameter\"}";
    }
    
    std::string path = path_match[1];
    
    try {
        GUI::Plater* plater = GUI::wxGetApp().plater();
        if (!plater) {
            return "{\"error\": \"Plater not available\"}";
        }
        
        // Export in GUI thread
        GUI::wxGetApp().CallAfter([plater]() {
            plater->export_gcode(false);
        });
        
        return "{\"success\": true, \"path\": \"" + path + "\"}";
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to export: " + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_get_status(const std::string& params)
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    try {
        GUI::Plater* plater = GUI::wxGetApp().plater();
        
        std::stringstream response;
        response << "{";
        response << "\"app_version\": \"" << SLIC3R_VERSION << "\", ";
        response << "\"has_model\": " << (plater && !plater->model().objects.empty() ? "true" : "false") << ", ";
        response << "\"object_count\": " << (plater ? plater->model().objects.size() : 0);
        response << "}";
        
        return response.str();
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to get status: " + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_load_file(const std::string& params)
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    // Extract path from params
    std::regex path_regex("\"path\"\\s*:\\s*\"([^\"]+)\"");
    std::smatch path_match;
    
    if (!std::regex_search(params, path_match, path_regex)) {
        return "{\"error\": \"Missing path parameter\"}";
    }
    
    std::string path = path_match[1];
    
    try {
        GUI::Plater* plater = GUI::wxGetApp().plater();
        if (!plater) {
            return "{\"error\": \"Plater not available\"}";
        }
        
        // Load file in GUI thread
        wxArrayString paths;
        paths.Add(wxString::FromUTF8(path.c_str()));
        
        GUI::wxGetApp().CallAfter([plater, paths]() {
            plater->load_files(paths);
        });
        
        return "{\"success\": true, \"path\": \"" + path + "\"}";
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to load file: " + std::string(e.what()) + "\"}";
    }
}

std::string ConfigServer::handle_list_config_keys()
{
    if (!m_gui_app) {
        return "{\"error\": \"GUI not initialized\"}";
    }
    
    try {
        const PresetBundle* preset_bundle = GUI::wxGetApp().preset_bundle.get();
        if (!preset_bundle) {
            return "{\"error\": \"Preset bundle not available\"}";
        }
        
        std::stringstream response;
        response << "{\"config_keys\": [";
        
        std::map<std::string, std::string> key_types;
        
        // Collect keys from print config
        const DynamicPrintConfig& print_config = preset_bundle->fff_prints.get_edited_preset().config;
        for (const auto& key : print_config.keys()) {
            key_types[key] = "print";
        }
        
        // Collect keys from filament config
        const DynamicPrintConfig& filament_config = preset_bundle->filaments.get_edited_preset().config;
        for (const auto& key : filament_config.keys()) {
            if (key_types.find(key) == key_types.end()) {
                key_types[key] = "filament";
            }
        }
        
        // Collect keys from printer config  
        const DynamicPrintConfig& printer_config = preset_bundle->printers.get_edited_preset().config;
        for (const auto& key : printer_config.keys()) {
            if (key_types.find(key) == key_types.end()) {
                key_types[key] = "printer";
            }
        }
        
        // Build JSON array with metadata
        bool first = true;
        for (const auto& [key, type] : key_types) {
            if (!first) response << ", ";
            
            response << "{\"key\": \"" << key << "\", ";
            response << "\"type\": \"" << type << "\"";
            
            // Add tooltip and metadata from config definition
            const ConfigOptionDef* def = print_config_def.get(key);
            if (def) {
                // Prepare tooltip
                std::string tooltip = def->tooltip;
                // Escape quotes in tooltip for JSON
                size_t pos = 0;
                while ((pos = tooltip.find('"', pos)) != std::string::npos) {
                    tooltip.replace(pos, 1, "\\\"");
                    pos += 2;
                }
                // Escape newlines
                pos = 0;
                while ((pos = tooltip.find('\n', pos)) != std::string::npos) {
                    tooltip.replace(pos, 1, "\\n");
                    pos += 2;
                }
                
                if (!tooltip.empty()) {
                    response << ", \"tooltip\": \"" << tooltip << "\"";
                }
                if (!def->label.empty()) {
                    response << ", \"label\": \"" << def->label << "\"";
                }
                if (!def->sidetext.empty()) {
                    response << ", \"unit\": \"" << def->sidetext << "\"";
                }
            }
            
            response << "}";
            first = false;
        }
        
        response << "]}";
        return response.str();
    }
    catch (const std::exception& e) {
        return "{\"error\": \"Failed to list config keys: " + std::string(e.what()) + "\"}";
    }
}
void ConfigServer::register_command_handler(const std::string& command, CommandCallback handler)
{
    m_command_handlers[command] = handler;
}

} // namespace Slic3r