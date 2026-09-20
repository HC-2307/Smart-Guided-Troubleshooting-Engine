def generate_troubleshooting_plan(enriched_query: dict) -> dict:
    # Placeholder plan, schema-conformant, pending real LLM planning (M1) and
    # catalog/deeplink matching (M2). Wiring here proves the API contract end
    # to end; content will be replaced once M1/M2 land.
    return {
        "contexts": [
            {
                "goal": "Follow these steps to perform this Battery Troubleshooting",
                "title": "Battery drain",
                "score": 0.5,
                "actions": [
                    {
                        "actionName": "Check Battery Usage",
                        "description": "It will show which apps drain battery",
                        "category": "auto",
                        "stepGroups": [
                            {
                                "steps": [
                                    "Open Settings",
                                    "Tap Battery and device care",
                                    "Tap Battery",
                                ]
                            }
                        ],
                    }
                ],
            }
        ]
    }
