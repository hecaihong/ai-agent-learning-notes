import json
import unittest

from agent import ContextAwareAgent, ToolRegistry


def local_agent():
    # Only exercise registration and dispatch; do not initialize an API client.
    agent = ContextAwareAgent.__new__(ContextAwareAgent)
    agent.tools = ToolRegistry()
    return agent


def test_revenue_tool_registration_and_dispatch():
    agent = local_agent()
    schemas = agent._get_tools_description()
    names = {schema['function']['name'] for schema in schemas}
    assert names == {'parse_pdf', 'convert_currency', 'calculate',
                     'code_interpreter', 'summarize_revenue'}
    json.dumps(schemas)
    result = agent._execute_tool('summarize_revenue', {
        'q1_usd': 2500000, 'q2_usd': 2282608.70,
        'q3_usd': 2278481.01, 'q4_usd': 2541806.02,
    })
    assert result == {'annual_total_usd': 9602895.73,
                      'quarter_average_usd': 2400723.93}


class RevenueToolTests(unittest.TestCase):
    def test_registration_and_dispatch(self):
        test_revenue_tool_registration_and_dispatch()

    def test_invalid_amounts(self):
        for value in [-1, '100', True, float('nan'), float('inf')]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                local_agent()._execute_tool('summarize_revenue', {
                    'q1_usd': value, 'q2_usd': 0, 'q3_usd': 0, 'q4_usd': 0,
                })

    def test_overflow(self):
        with self.assertRaises(ValueError):
            local_agent()._execute_tool('summarize_revenue', {
                'q1_usd': 1e308, 'q2_usd': 1e308, 'q3_usd': 0, 'q4_usd': 0,
            })


if __name__ == '__main__':
    unittest.main()
