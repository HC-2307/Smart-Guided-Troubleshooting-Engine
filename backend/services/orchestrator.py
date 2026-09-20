def call_m1(query: str):
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
            }
        ]
    }

def troubleshoot(query: str):
    m1_result = call_m1(query)

    return m1_result