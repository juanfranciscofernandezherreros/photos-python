Feature: User management
  As the administrator I want to register users and control access,
  and there must only ever be one administrator.

  Background:
    Given the API is running

  Scenario: First run has no admin
    When I request GET "/api/auth/status"
    Then the response status is 200
    And "admin_exists" is false

  Scenario: Creating the first admin succeeds
    When I setup an admin "root" with password "supersecret"
    Then the response status is 200
    And the created user role is "admin"

  Scenario: A second admin cannot be created via setup
    Given an admin "root" exists with password "supersecret"
    When I setup an admin "root2" with password "supersecret"
    Then the response status is 403

  Scenario: Admin registers a normal user who can then log in
    Given an admin "root" exists with password "supersecret"
    When I register a user "alice" with password "alicepass1" role "user"
    Then the response status is 200
    When I log out
    And I log in as "alice" with password "alicepass1"
    Then the response status is 200

  Scenario: A normal user cannot access admin config
    Given an admin "root" exists with password "supersecret"
    And a user "bob" exists with password "bobpass123"
    When I log in as "bob" with password "bobpass123"
    And I request GET "/api/ssh"
    Then the response status is 403

  Scenario: A normal user can view the shared gallery
    Given an admin "root" exists with password "supersecret"
    And a user "bob" exists with password "bobpass123"
    When I log in as "bob" with password "bobpass123"
    And I request GET "/api/days"
    Then the response status is 200
