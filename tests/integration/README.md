# Integration Testing Framework

## Overview

This directory contains the integration testing framework for the Space Station Cargo Management System. The integration tests verify that all system components work together correctly, ensuring end-to-end functionality and system stability.

## Directory Structure

```
tests/
├── integration/
│   ├── framework.py                  # Base testing infrastructure
│   ├── test_item_lifecycle.py        # Tests for complete item lifecycle
│   ├── test_rearrangement.py         # Tests for space optimization and rearrangement
│   └── test_error_handling.py        # Tests for error handling and system stability
├── run_integration_tests.py          # Test runner script
└── README.md                         # This file
```

## Test Categories

The integration tests cover several key workflows and system aspects:

### Item Lifecycle Integration Tests
Verifies the end-to-end functionality of items through their complete lifecycle:
1. Import items and containers
2. Optimize item placement
3. Search and retrieve items
4. Track usage and expiration
5. Identify waste items
6. Plan waste return
7. Complete undocking

### Rearrangement Integration Tests
Verifies the complex workflows involving rearrangement operations:
1. Placing items when space is constrained
2. Rearranging existing items to optimize space utilization
3. Moving items based on priority
4. Verifying placements after rearrangement

### Error Handling Integration Tests
Verifies the system's ability to handle various error conditions and maintain stability:
1. Validation of inputs at API boundaries
2. Graceful handling of invalid data
3. Error recovery mechanisms
4. System stability under edge case scenarios

## Running the Tests

### Prerequisites

- Python 3.8 or higher
- Project dependencies installed (`pip install -r requirements.txt`)
- PostgreSQL database (or SQLite for testing)

### Using the Test Runner

The test runner script provides a convenient way to run all integration tests and generate a comprehensive report.

```bash
# Run all integration tests
python tests/run_integration_tests.py

# Run with verbose output
python tests/run_integration_tests.py --verbose

# Skip slow tests
python tests/run_integration_tests.py --skip-slow

# Specify custom test and report directories
python tests/run_integration_tests.py --test-dir ./tests/integration --report-dir ./reports
```

### Test Reports

After running the tests, the test runner generates several reports:

1. **XML Report**: Contains detailed test results in JUnit XML format
2. **JSON Report**: Contains structured test results for programmatic processing
3. **HTML Report**: User-friendly visual report showing test status and details

Reports are saved in the `reports/` directory by default.

## Writing New Integration Tests

### Creating a New Test Suite

1. Create a new Python file in the `tests/integration/` directory with the name pattern `test_*.py`
2. Import the necessary components from the framework:
   ```python
   from tests.integration.framework import IntegrationTestFixture, client
   ```
3. Create a test class that inherits from `IntegrationTestFixture`
4. Implement test methods that start with `test_`

### Example Test

```python
import pytest
from tests.integration.framework import IntegrationTestFixture, client

class TestExampleIntegration(IntegrationTestFixture):
    def test_example_workflow(self):
        # Step 1: Set up test data
        container = self.create_container(id="test_cont")
        item = self.create_item(id="test_item")
        
        # Step 2: Execute API calls
        response = client.get(f"/api/search?itemId={item.id}")
        result = self.assert_request_success(response)
        
        # Step 3: Verify results
        assert not result["found"], "Item should not be found yet"
        
        # Step 4: Continue workflow
        # ...
```

### Test Fixture Methods

The `IntegrationTestFixture` class provides several helper methods:

- `create_container(**kwargs)`: Create a test container
- `create_item(**kwargs)`: Create a test item
- `create_position(**kwargs)`: Create a test position
- `create_test_scenario(scenario_name)`: Create a predefined test scenario
- `assert_request_success(response)`: Assert that an API request was successful
- `api_get(endpoint, **kwargs)`: Make a GET request to the API
- `api_post(endpoint, json_data, **kwargs)`: Make a POST request to the API

## Troubleshooting

### Database Issues

The integration tests use an in-memory SQLite database by default. To use a different database:

1. Set the `TEST_DATABASE_URL` environment variable:
   ```bash
   export TEST_DATABASE_URL="postgresql://user:password@localhost/test_db"
   ```

2. Run the tests:
   ```bash
   python tests/run_integration_tests.py
   ```

### Test Isolation

Each test method runs in isolation with a fresh database. If you experience test interference:

1. Check that your test methods don't depend on data created by other tests
2. Ensure proper cleanup in the `teardown_method` if you've added custom resources
3. Verify that database transactions are properly committed or rolled back

## Best Practices

1. **Test Complete Workflows**: Focus on testing end-to-end user scenarios rather than individual functions
2. **Verify System State**: After operations, verify the system state using search/retrieval APIs
3. **Error Handling**: Include tests for error conditions and edge cases
4. **Document Test Steps**: Add clear comments describing each step in the test
5. **Avoid Test Dependencies**: Each test should be independent and not rely on other tests
