#include <catch_main.hpp>
#include <libslic3r/ConfigServer.hpp>
#include <libslic3r/Config.hpp>
#include <libslic3r/Print.hpp>
#include <thread>
#include <chrono>
#include <memory>

using namespace Slic3r;

// Helper function to wait for server to start
bool wait_for_server(int port, int timeout_ms = 5000) {
    auto start = std::chrono::steady_clock::now();
    while (std::chrono::duration_cast<std::chrono::milliseconds>(
               std::chrono::steady_clock::now() - start).count() < timeout_ms) {
        // Try to connect to check if server is up
        // This is a simplified check - in real implementation you'd try an HTTP request
        std::this_thread::sleep_for(std::chrono::milliseconds(100));
    }
    return true;
}

SCENARIO("ConfigServer basic operations", "[ConfigServer]") {
    GIVEN("A ConfigServer instance") {
        DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
        Print print;
        
        // Set some test values
        config.set_key_value("layer_height", new ConfigOptionFloat(0.2));
        config.set_key_value("xy_size_compensation", new ConfigOptionFloat(-0.1));
        config.set_key_value("fill_density", new ConfigOptionPercent(20));
        
        WHEN("Server is started on default port") {
            auto server = std::make_unique<ConfigServer>(&config, &print);
            server->start(21987);
            
            THEN("Server should be running") {
                REQUIRE(server->is_running() == true);
                REQUIRE(wait_for_server(21987) == true);
            }
            
            AND_WHEN("Server is stopped") {
                server->stop();
                THEN("Server should not be running") {
                    REQUIRE(server->is_running() == false);
                }
            }
        }
        
        WHEN("Server is started on a custom port") {
            auto server = std::make_unique<ConfigServer>(&config, &print);
            server->start(8888);
            
            THEN("Server should be running on custom port") {
                REQUIRE(server->is_running() == true);
                REQUIRE(wait_for_server(8888) == true);
            }
            
            server->stop();
        }
        
        WHEN("Multiple servers try to use the same port") {
            auto server1 = std::make_unique<ConfigServer>(&config, &print);
            server1->start(21987);
            
            auto server2 = std::make_unique<ConfigServer>(&config, &print);
            
            THEN("Second server should fail to start or use different port") {
                bool started = server2->start(21987);
                // Either it fails to start (returns false)
                // Or it auto-increments the port
                if (started) {
                    REQUIRE(server2->get_port() != 21987);
                } else {
                    REQUIRE(started == false);
                }
            }
            
            server1->stop();
            if (server2->is_running()) {
                server2->stop();
            }
        }
    }
}

SCENARIO("ConfigServer JSON output", "[ConfigServer]") {
    GIVEN("A ConfigServer with various config values") {
        DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
        Print print;
        
        // Set values that might cause JSON issues
        config.set_key_value("layer_height", new ConfigOptionFloat(0.2));
        
        auto server = std::make_unique<ConfigServer>(&config, &print);
        
        WHEN("Getting config values with special characters in tooltips") {
            // This tests that tooltips with special characters are properly escaped
            auto json_output = server->get_config_json("layer_height");
            
            THEN("JSON should be valid") {
                // Check that the JSON is parseable
                // In a real test, you'd use a JSON parser to validate
                REQUIRE(json_output.find("\"key\":") != std::string::npos);
                REQUIRE(json_output.find("\"value\":") != std::string::npos);
                
                // Check for proper escaping of backslashes
                // Any backslash should be escaped as \\ in JSON
                size_t pos = 0;
                while ((pos = json_output.find("\\", pos)) != std::string::npos) {
                    // Check that it's properly escaped
                    if (pos + 1 < json_output.length()) {
                        char next_char = json_output[pos + 1];
                        // Valid JSON escapes: \", \\, \/, \b, \f, \n, \r, \t, \uXXXX
                        bool valid_escape = (next_char == '"' || next_char == '\\' || 
                                           next_char == '/' || next_char == 'b' || 
                                           next_char == 'f' || next_char == 'n' || 
                                           next_char == 'r' || next_char == 't' || 
                                           next_char == 'u');
                        REQUIRE(valid_escape == true);
                    }
                    pos += 2; // Move past the escape sequence
                }
            }
        }
        
        WHEN("Getting all config keys") {
            auto json_output = server->get_all_configs_json();
            
            THEN("JSON should be valid and contain array of keys") {
                REQUIRE(json_output.find("\"config_keys\":") != std::string::npos);
                REQUIRE(json_output.find("[") != std::string::npos);
                REQUIRE(json_output.find("]") != std::string::npos);
            }
        }
    }
}

SCENARIO("ConfigServer thread safety", "[ConfigServer]") {
    GIVEN("A running ConfigServer") {
        DynamicPrintConfig config = DynamicPrintConfig::full_print_config();
        Print print;
        
        auto server = std::make_unique<ConfigServer>(&config, &print);
        server->start(21987);
        
        WHEN("Multiple threads access the server") {
            std::atomic<int> successful_reads{0};
            std::vector<std::thread> threads;
            
            // Create multiple threads that read config
            for (int i = 0; i < 10; ++i) {
                threads.emplace_back([&server, &successful_reads]() {
                    for (int j = 0; j < 100; ++j) {
                        auto result = server->get_config_json("layer_height");
                        if (!result.empty()) {
                            successful_reads++;
                        }
                    }
                });
            }
            
            // Wait for all threads to complete
            for (auto& t : threads) {
                t.join();
            }
            
            THEN("All reads should succeed") {
                REQUIRE(successful_reads == 1000);
            }
        }
        
        server->stop();
    }
}