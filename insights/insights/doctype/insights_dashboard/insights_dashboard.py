# Copyright (c) 2022, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt


import frappe
from json import dumps
from frappe.model.document import Document


class InsightsDashboard(Document):
    @frappe.whitelist()
    def get_charts(self):
        charts = [
            row.chart for row in self.items if row.item_type == "Chart" and row.chart
        ]
        return frappe.get_all(
            "Insights Query Chart",
            filters={"name": ("not in", charts), "type": ["!=", "Pivot"]},
            fields=["name", "title", "type"],
        )

    @frappe.whitelist()
    def add_item(self, item, layout=None):
        if not layout:
            layout = {"w": 8, "h": 8}
        self.append(
            "items",
            {
                **item,
                "layout": dumps(layout, indent=2),
            },
        )
        self.save()

    @frappe.whitelist()
    def refresh_items(self):
        for item in self.items:
            try:
                frappe.get_doc("Insights Query", item.query).run()
            except BaseException:
                frappe.log_error(title="Error while refreshing dashboard item")

    @frappe.whitelist()
    def remove_item(self, item):
        for row in self.items:
            if row.name == item:
                self.remove(row)
                self.save()
                break

    @frappe.whitelist()
    def update_layout(self, updated_layout):
        updated_layout = frappe._dict(updated_layout)
        if not updated_layout:
            return

        for row in self.items:
            # row.name can be an interger which could get converted to a string
            if str(row.name) in updated_layout or row.name in updated_layout:
                new_layout = (
                    updated_layout.get(str(row.name))
                    or updated_layout.get(row.name)
                    or {}
                )
                row.layout = dumps(new_layout, indent=2)
        self.save()

    @frappe.whitelist()
    def update_filter(self, filter):
        filter = frappe._dict(filter)
        for row in self.items:
            if row.name == filter.name:
                row.filter_label = filter.label
                row.filter_type = filter.type
                row.filter_operator = filter.operator
                row.filter_value = filter.value
                self.save()
                break

    @frappe.whitelist()
    def update_chart_filters(self, chart, filters):
        filters = frappe.parse_json(filters)
        for row in self.items:
            if row.name == chart:
                row.chart_filters = dumps(filters, indent=2)
                self.save()
                break

    @frappe.whitelist()
    def get_columns_for(self, query):
        return frappe.get_doc("Insights Query", query).fetch_columns()

    @frappe.whitelist()
    def get_chart_data(self, chart):
        row = self.get("items", {"chart": chart})[0]
        if chart_filters := frappe.parse_json(row.chart_filters):
            query = frappe.get_doc("Insights Query", row.query)
            filter_conditions = []
            for chart_filter in chart_filters:
                filter = self.get(
                    "items",
                    {
                        "item_type": "Filter",
                        "filter_label": chart_filter.get("filter"),
                    },
                )[0]
                if not filter.filter_value:
                    continue
                table, column = chart_filter.get("column").split(".")
                filter_conditions.append(convert_to_expression(table, column, filter))
            return query.run_with_filters(filter_conditions)
        else:
            return frappe.db.get_value("Insights Query", row.query, "result")


BINARY_OPERATORS = [
    "=",
    "!=",
    "<",
    ">",
    "<=",
    ">=",
]

FUNCTION_OPERATORS = [
    "is",
    "in",
    "not_in",
    "between",
    "timespan",
    "starts_with",
    "ends_with",
    "contains",
    "not_contains",
]


def convert_to_expression(table, column, filter):
    if filter.filter_operator in BINARY_OPERATORS:
        return make_binary_expression(table, column, filter)
    if filter.filter_operator in FUNCTION_OPERATORS:
        return make_call_expression(table, column, filter)


def make_binary_expression(table, column, filter):
    return {
        "type": "BinaryExpression",
        "operator": filter.filter_operator,
        "left": {
            "type": "Column",
            "value": {
                "column": column,
                "table": table,
            },
        },
        "right": {
            "type": "Number"
            if filter.filter_type in ("Integer", "Decimal")
            else "String",
            "value": filter.filter_value,
        },
    }


def make_call_expression(table, column, filter):
    operator_function = filter.filter_operator
    if filter.filter_operator == "is":
        operator_function = "is_set" if filter.filter_value == "set" else "is_not_set"

    return {
        "type": "CallExpression",
        "function": operator_function,
        "arguments": [
            {
                "type": "Column",
                "value": {
                    "column": column,
                    "table": table,
                },
            },
            *make_args_for_call_expression(operator_function, filter),
        ],
    }


def make_args_for_call_expression(operator_function, filter):
    if operator_function == "is":
        return []

    if operator_function == "between":
        values = filter.filter_value.split(",")
        return [
            {
                "type": "Number" if filter.filter_type == "Number" else "String",
                "value": v,
            }
            for v in values
        ]

    if operator_function in ["in", "not_in"]:
        return [{"type": "String", "value": v} for v in filter.filter_value]

    return [
        {
            "type": "Number" if filter.filter_type == "Number" else "String",
            "value": filter.filter_value,
        }
    ]
