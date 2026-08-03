Feature: SSH Connections
  As a user I want to manage SSH server connections used as photo sources or destinations.

  Background:
    Given the API is running

  Scenario: SSH list is empty initially
    When I request GET "/api/ssh"
    Then the response status is 200
    And the response is an empty list

  Scenario: Get SSH roles
    When I request GET "/api/ssh/roles"
    Then the response status is 200
    And the JSON has key "roles" with a list

  Scenario: Create an SSH connection
    When I POST "/api/ssh" with alias "nas" host "192.168.1.50" port 22 user "juan" source "/fotos" role "origen"
    Then the response status is 200
    When I request GET "/api/ssh"
    Then the response contains 1 connection with alias "nas"

  Scenario: Creating duplicate alias overwrites
    When I POST "/api/ssh" with alias "nas" host "10.0.0.1" port 22 user "root" source "/img" role "origen"
    And I POST "/api/ssh" with alias "nas" host "10.0.0.2" port 22 user "admin" source "/pics" role "destino"
    When I request GET "/api/ssh"
    Then there is exactly 1 connection
    And its host is "10.0.0.2"

  Scenario: Delete an SSH connection
    When I POST "/api/ssh" with alias "tmp" host "1.2.3.4" port 22 user "u" source "/a" role "origen"
    And I DELETE "/api/ssh/tmp"
    Then the response status is 200
    When I request GET "/api/ssh"
    Then the response is an empty list

  Scenario: Delete nonexistent SSH is idempotent
    When I DELETE "/api/ssh/nonexistent"
    Then the response status is 200
