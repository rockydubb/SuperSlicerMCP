#ifndef slic3r_ConfigServer_hpp_
#define slic3r_ConfigServer_hpp_

#include <string>
#include <thread>
#include <atomic>
#include <memory>
#include <functional>
#include <boost/asio.hpp>
#include <map>

namespace Slic3r {

class DynamicPrintConfig;
class PresetBundle;
class Model;
class Print;

namespace GUI {
class GUI_App;
class Plater;
class MainFrame;
}

class ConfigServer
{
public:
    using ConfigUpdateCallback = std::function<void(const std::string& key, const std::string& value)>;
    using CommandCallback = std::function<std::string(const std::string& command, const std::string& params)>;

    ConfigServer();
    ~ConfigServer();

    // Start the server on the specified port
    bool start(uint16_t port = 21987);
    
    // Stop the server
    void stop();
    
    // Check if server is running
    bool is_running() const { return m_running.load(); }
    
    // Get the port the server is listening on
    uint16_t get_port() const { return m_port; }
    
    // Get the unique instance ID
    const std::string& get_instance_id() const { return m_instance_id; }
    
    // Set the GUI app reference for accessing configuration
    void set_gui_app(GUI::GUI_App* app) { m_gui_app = app; }
    
    // Set callbacks
    void set_config_update_callback(ConfigUpdateCallback callback) { m_config_update_callback = callback; }
    void set_command_callback(CommandCallback callback) { m_command_callback = callback; }

    // Register custom command handlers
    void register_command_handler(const std::string& command, CommandCallback handler);
    
private:
    void run_server();
    void handle_client(std::shared_ptr<boost::asio::ip::tcp::socket> socket);
    std::string process_command(const std::string& json_request);
    
    // Instance registry management
    void register_instance();
    void unregister_instance();
    static std::string get_registry_dir();
    static std::string get_instance_file_path(const std::string& instance_id);
    static void cleanup_stale_instances();
    
    std::string handle_get_config(const std::string& params);
    std::string handle_set_config(const std::string& params);
    std::string handle_get_preset(const std::string& params);
    std::string handle_list_presets(const std::string& params);
    std::string handle_slice(const std::string& params);
    std::string handle_export(const std::string& params);
    std::string handle_get_status(const std::string& params);
    std::string handle_load_file(const std::string& params);
    std::string handle_list_config_keys();
    std::string handle_list_instances(const std::string& params);
    
    std::atomic<bool> m_running{false};
    std::unique_ptr<std::thread> m_server_thread;
    uint16_t m_port{21987};
    std::string m_instance_id;  // Unique identifier for this instance
    
    GUI::GUI_App* m_gui_app{nullptr};
    
    ConfigUpdateCallback m_config_update_callback;
    CommandCallback m_command_callback;
    std::map<std::string, CommandCallback> m_command_handlers;
    
    std::unique_ptr<boost::asio::io_context> m_io_context;
    std::unique_ptr<boost::asio::ip::tcp::acceptor> m_acceptor;
};

} // namespace Slic3r

#endif // slic3r_ConfigServer_hpp_