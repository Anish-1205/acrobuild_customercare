import unittest

from services.ai_agent_service import build_company_api_direct_answer
from graph.haystack_conversation_pipeline import resolve_contextual_support_issue


def chunk(name, project_id, home_type, area, rate):
    return {
        "source_key": f"acrobuild-cs-project-{project_id}",
        "project_name": name,
        "project": {"id": project_id, "projectName": name},
        "inventory_loaded": True,
        "typologies": [{"id": project_id, "minBasePrice": rate, "saleableArea": area}],
        "available_inventory": [{
            "id": project_id, "typologyId": project_id, "typologyType": home_type,
            "saleableArea": area, "statusLabel": "Available",
        }],
    }


class BudgetProjectRecommendationTests(unittest.TestCase):
    def test_project_count_uses_live_catalogue_count(self):
        chunks = [{
            "source_key": "acrobuild-cs-projects",
            "record_count": 9,
            "projects": [{"id": value} for value in range(9)],
            "project_names": [f"Project {value}" for value in range(9)],
        }]

        answer = build_company_api_direct_answer("How many project available", chunks, [])

        self.assertEqual("There are currently 9 projects available in the live Acrobuild CS API.", answer)

    def test_budget_follow_up_is_not_rewritten_as_project_overview(self):
        issue = "My budget is 50 lakh rupees is it sufficient to buy it"
        history = [
            {"sender": "customer", "text": "Show a project with both 1BHK and 2BHK"},
            {"sender": "bot", "text": "Vishwajeet Myspace has both configurations."},
        ]

        self.assertEqual(issue, resolve_contextual_support_issue(issue, history))

    def test_budget_follow_up_compares_both_recommended_homes(self):
        history = [{
            "sender": "bot",
            "text": (
                "Vishwajeet Myspace is the most budget-friendly project I found with live availability "
                "for both 1BHK and 2BHK:\n\n"
                "- 1BHK: 660 sq. ft. at INR 2,900 per sq. ft.\n"
                "  Estimated base amount: INR 19.14 lakh\n\n"
                "- 2BHK: 806 sq. ft. at INR 2,900 per sq. ft.\n"
                "  Estimated base amount: INR 23.37 lakh"
            ),
        }]

        answer = build_company_api_direct_answer(
            "My budget is 50 lakh rupees is it sufficient to buy it", [], history,
        )

        self.assertIn("Yes", answer)
        self.assertIn("combined base amount of INR 42.51 lakh", answer)
        self.assertIn("INR 7.49 lakh", answer)
        self.assertIn("additional charges", answer)

    def test_budget_friendly_project_with_both_bhk_types_returns_both(self):
        empire_1bhk = chunk("Vishwajeet Empire", 2, "1BHK", 588, 2800)
        empire_1bhk["typologies"].append({"id": 22, "minBasePrice": 3500, "saleableArea": 900})
        empire_1bhk["available_inventory"].append({
            "id": 22, "typologyId": 22, "typologyType": "2BHK",
            "saleableArea": 900, "statusLabel": "Available",
        })
        chunks = [
            empire_1bhk,
            chunk("Only One BHK", 3, "1BHK", 500, 2500),
            chunk("Only Two BHK", 4, "2BHK", 800, 3000),
        ]

        answer = build_company_api_direct_answer(
            "Best budget friendly which is having both 1BHK and 2BHK", chunks, [],
        )

        self.assertIn("Vishwajeet Empire", answer)
        self.assertIn("both 1BHK and 2BHK", answer)
        self.assertIn("- 1BHK:", answer)
        self.assertIn("- 2BHK:", answer)
        self.assertNotIn("Only One BHK", answer)

    def test_budget_friendly_project_uses_live_comparable_pricing(self):
        chunks = [
            chunk("Vishwajeet Paradise", 1, "1RK+T", 527, 3000),
            chunk("Vishwajeet Empire", 2, "1BHK", 588, 2800),
            chunk("Vishwajeet Prime", 3, "2BHK", 1290, 4000),
        ]
        answer = build_company_api_direct_answer(
            "Can you suggest me your best project which is budget friendly", chunks, [],
        )
        self.assertIn("Vishwajeet Paradise", answer)
        self.assertIn("INR 15.81 lakh", answer)
        self.assertIn("specifically want a 1 BHK", answer)
        self.assertIn("Vishwajeet Empire", answer)
        self.assertIn("Taxes, registration", answer)
        self.assertNotIn("projects available to explore", answer)

    def test_shop_is_excluded_from_residential_budget_recommendation(self):
        chunks = [
            chunk("Shop Project", 1, "Shop", 100, 1000),
            chunk("Home Project", 2, "1BHK", 500, 3000),
        ]
        answer = build_company_api_direct_answer("Suggest best budget project", chunks, [])
        self.assertIn("Home Project", answer)
        self.assertNotIn("Shop Project", answer)

    def test_missing_live_pricing_is_disclosed(self):
        answer = build_company_api_direct_answer(
            "Suggest best affordable project", [{"project_name": "A", "inventory_loaded": False}], [],
        )
        self.assertIn("could not calculate a grounded", answer.lower())


if __name__ == "__main__":
    unittest.main()
