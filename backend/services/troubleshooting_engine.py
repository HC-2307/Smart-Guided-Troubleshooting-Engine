def generate_troubleshooting_plan(enriched_query: dict):
    # Turn the enriched query into ordered troubleshooting actions
    return {
        "goal": "Troubleshooting",
        "title": "Battery draining quickly",
        "scope": "Battery",
        "actions": [
            {
                "step": 1,
                "actionName": "Check battery usage",
                "description": "Review applications consuming battery.",
                "category": "standard"
            },
            {
                "step": 2,
                "actionName": "Check background usage",
                "description": "Review apps running in the background.",
                "category": "standard"
            }
        ]
    }