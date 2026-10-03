"""Offline dashboard contract checks for JSON, resource dimensions and layout."""
import json
from pathlib import Path
import re
import unittest

import yaml


class CfnLoader(yaml.SafeLoader):
    pass


def cfn_tag(loader, tag, node):
    name = "Ref" if tag == "Ref" else "Fn::" + tag
    if isinstance(node, yaml.ScalarNode):
        value = loader.construct_scalar(node)
    elif isinstance(node, yaml.SequenceNode):
        value = loader.construct_sequence(node)
    else:
        value = loader.construct_mapping(node)
    return {name: value}


CfnLoader.add_multi_constructor("!", cfn_tag)


class OperationsDashboardTests(unittest.TestCase):
    def setUp(self):
        self.template = yaml.load(
            (Path(__file__).resolve().parents[1] / "template.yaml").read_text(),
            Loader=CfnLoader,
        )
        self.resource = self.template["Resources"]["OperationsDashboard"]
        self.body_text = self.resource["Properties"]["DashboardBody"]["Fn::Sub"]
        self.body = json.loads(self.body_text)
        self.metric_widgets = [w for w in self.body["widgets"] if w["type"] == "metric"]

    def test_stack_scoped_dimensions_and_real_http_api_metric_names(self):
        resources = self.template["Resources"]
        expected_functions = {name for name, r in resources.items()
                              if r["Type"] == "AWS::Serverless::Function"}
        error_functions, state_machines, api_metrics = set(), set(), set()
        metric_count = 0
        for widget in self.metric_widgets:
            props = widget["properties"]
            self.assertEqual(props["region"], "${AWS::Region}")
            for metric in props["metrics"]:
                metric_count += 1
                namespace, name, dimension, resource_ref = metric[:4]
                self.assertRegex(resource_ref, r"^\$\{\w+\}$")
                logical_id = resource_ref[2:-1]
                self.assertIn(logical_id, resources)
                if namespace == "AWS/Lambda":
                    self.assertEqual(dimension, "FunctionName")
                    self.assertEqual(resources[logical_id]["Type"], "AWS::Serverless::Function")
                    if name == "Errors":
                        error_functions.add(logical_id)
                elif namespace == "AWS/States":
                    self.assertEqual(dimension, "StateMachineArn")
                    self.assertEqual(resources[logical_id]["Type"], "AWS::Serverless::StateMachine")
                    state_machines.add(logical_id)
                elif namespace == "AWS/ApiGateway":
                    self.assertEqual((dimension, logical_id), ("ApiId", "HttpApi"))
                    api_metrics.add(name)
                elif namespace == "AWS/DynamoDB":
                    self.assertEqual((dimension, logical_id), ("TableName", "LedgerTable"))
                    self.assertIn(name, {"ReadThrottleEvents", "WriteThrottleEvents"})
                else:
                    self.fail(f"unexpected namespace {namespace}")
        self.assertEqual(error_functions, expected_functions)
        self.assertEqual(state_machines, {"IngestDocumentStateMachine", "ApproveBillStateMachine"})
        self.assertEqual(api_metrics, {"Count", "4xx", "5xx", "Latency", "IntegrationLatency"})
        self.assertLessEqual(metric_count, 50)

    def test_substitution_resolves_to_valid_json_for_another_stage_and_region(self):
        values = {"AWS::Region": "us-west-2", "AWS::StackName": "ledgerline-test",
                  "Stage": "test"}
        values.update({name: f"physical-{name}" for name in self.template["Resources"]})
        resolved = re.sub(r"\$\{([^}]+)\}", lambda m: values[m.group(1)], self.body_text)
        body = json.loads(resolved)
        self.assertNotIn("${", resolved)
        self.assertEqual(body["start"], "-PT3H")
        for widget in body["widgets"]:
            if widget["type"] == "metric":
                self.assertEqual(widget["properties"]["region"], "us-west-2")
        self.assertEqual(self.resource["Type"], "AWS::CloudWatch::Dashboard")
        name = self.resource["Properties"]["DashboardName"]["Fn::Sub"]
        self.assertIn("${AWS::StackName}", name)
        self.assertIn("${AWS::Region}", name)
        self.assertEqual(self.template["Outputs"]["OperationsDashboardName"]["Value"],
                         {"Ref": "OperationsDashboard"})

    def test_widgets_do_not_overlap_or_exceed_grid(self):
        widgets = self.body["widgets"]
        for i, a in enumerate(widgets):
            self.assertGreater(a["width"], 0)
            self.assertLessEqual(a["x"] + a["width"], 24)
            for b in widgets[i + 1:]:
                overlaps = (max(a["x"], b["x"]) < min(a["x"] + a["width"], b["x"] + b["width"])
                            and max(a["y"], b["y"]) < min(a["y"] + a["height"], b["y"] + b["height"]))
                self.assertFalse(overlaps)


if __name__ == "__main__":
    unittest.main()
