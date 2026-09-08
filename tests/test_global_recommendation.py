import unittest

from services.ai_agent_service import (
    build_company_api_direct_answer,
    build_contextual_assist_query,
    is_local_product_feed_recommendation_question,
    is_lowest_property_value_request,
    is_highest_property_value_request,
    is_cross_project_floor_comparison_request,
)


class GlobalRecommendationTests(unittest.TestCase):
    def setUp(self):
        self.history = [
            {"sender": "customer", "text": "Venus A"},
            {"sender": "bot", "text": "Choose a floor to continue"},
            {"sender": "customer", "text": "Floor 3"},
        ]
        self.chunks = [
            self.project_chunk("Project Alpha", 1, "Alpha Wing", 2, "201", 2_900, 900, "2BHK"),
            self.project_chunk("Project Beta", 2, "Beta Wing", 1, "101", 2_500, 800, "2BHK"),
            self.project_chunk("Project Gamma", 3, "Gamma Wing", 1, "102", 2_000, 500, "1BHK"),
        ]

    @staticmethod
    def project_chunk(name, identifier, wing_name, floor, unit_number, rate, area, home_type):
        return {
            "source_key": f"acrobuild-cs-project-{identifier}",
            "project_name": name,
            "inventory_loaded": True,
            "wings": [{"id": identifier, "name": wing_name}],
            "typologies": [{
                "id": identifier,
                "typologyName": home_type,
                "typologyType": home_type,
                "minBasePrice": rate,
                "maxBasePrice": rate,
                "saleableArea": area,
            }],
            "available_inventory": [{
                "typologyId": identifier,
                "typologyName": home_type,
                "wingId": identifier,
                "floorNumber": floor,
                "unitNumber": unit_number,
                "saleableArea": area,
            }],
        }

    def test_global_2bhk_request_does_not_inherit_old_floor(self):
        issue = "Give me best effordable best 2BHK Flat in your all projects"
        answer = build_company_api_direct_answer(issue, self.chunks, self.history)

        self.assertIn("Project: Project Beta", answer)
        self.assertIn("Floor: 1", answer)
        self.assertNotIn("Project Alpha", answer)

    def test_global_affordable_request_without_bhk_returns_one_live_home(self):
        issue = "Give me a best affordable flat in your entire projects"
        answer = build_company_api_direct_answer(issue, self.chunks, self.history)

        self.assertIn("Project Gamma", answer)
        self.assertIn("lowest estimated starting value", answer)
        self.assertNotIn("quick overview", answer.lower())

    def test_exact_flat_survives_intervening_project_overview(self):
        first_issue = "Show the highest cost flat in all projects"
        first_answer = build_company_api_direct_answer(first_issue, self.chunks, [])
        recommended_project = next(
            name for name in ("Project Alpha", "Project Beta", "Project Gamma")
            if name in first_answer
        )
        history = [
            {"sender": "customer", "text": first_issue},
            {"sender": "bot", "text": first_answer},
            {"sender": "customer", "text": f"Tell me more about project {recommended_project}"},
            {"sender": "bot", "text": f"Sure - here is a verified overview of {recommended_project}. Home types: 2BHK."},
        ]
        answer = build_company_api_direct_answer(
            "Is this flat still available?",
            self.chunks,
            history,
        )
        self.assertIn("rechecked the current inventory", answer)
        self.assertIn("still showing as available", answer)
        self.assertNotIn("currently available on", answer)
    def test_follow_ups_stay_bound_to_primary_recommendation(self):
        first_issue = "Most affordable 2BHK in all projects"
        first_answer = build_company_api_direct_answer(first_issue, self.chunks, [])
        history = [
            {"sender": "customer", "text": first_issue},
            {"sender": "bot", "text": first_answer},
        ]

        second_issue = "This 2BHK flat that you showed, which flat is it?"
        second_answer = build_company_api_direct_answer(second_issue, self.chunks, history)
        self.assertIn("Project Beta", second_answer)
        self.assertNotIn("Project Alpha", second_answer)

        history.extend([
            {"sender": "customer", "text": second_issue},
            {"sender": "bot", "text": second_answer},
        ])
        third_answer = build_company_api_direct_answer(
            "Sorry, which floor is it?",
            self.chunks,
            history,
        )
        self.assertIn("Project Beta", third_answer)
        self.assertIn("floor 1", third_answer.lower())
        self.assertNotIn("Project Alpha", third_answer)
    def test_implicit_scope_lowest_flat_question_loads_live_pricing(self):
        issue = "What is the price of your lowest flat that u have in your project"

        contextual = build_contextual_assist_query(issue, [])
        self.assertIn("live availability pricing", contextual)

        answer = build_company_api_direct_answer(issue, self.chunks, [])
        self.assertIn("most affordable available home", answer)
        self.assertIn("Project Gamma", answer)
        self.assertIn("estimated starting base value", answer)
    def test_price_comparison_paraphrases_share_semantic_intent(self):
        low_queries = [
            "What is the Low cost Flat in the entire projects and what is the price of it",
            "Show the cheapest available home across all projects",
            "Which property has the minimum value in every project?",
            "Give me an economical flat across your projects",
        ]
        high_queries = [
            "Show the highest cost flat in all projects",
            "Which is the most expensive available home across projects?",
            "Give me a costly property in the entire project list",
            "What premium home has the maximum value across all?",
        ]

        for issue in low_queries:
            with self.subTest(issue=issue):
                self.assertTrue(is_lowest_property_value_request(issue))
                contextual = build_contextual_assist_query(issue, [])
                self.assertIn("live availability pricing", contextual)
                answer = build_company_api_direct_answer(issue, self.chunks, [])
                self.assertIn("most affordable available home", answer)
                self.assertIn("Project Gamma", answer)

        for issue in high_queries:
            with self.subTest(issue=issue):
                self.assertTrue(is_highest_property_value_request(issue))
                contextual = build_contextual_assist_query(issue, [])
                self.assertIn("live availability pricing", contextual)
                answer = build_company_api_direct_answer(issue, self.chunks, [])
                self.assertIn("highest-priced available home", answer)
                self.assertIn("Project Alpha", answer)
    def test_costly_flat_across_entire_projects_ignores_old_project_context(self):
        history = [
            {"sender": "customer", "text": "Show 2BHK in Project Beta"},
            {"sender": "bot", "text": "Project Beta has available 2 BHK units."},
        ]
        issue = "What is the costly Flat in the entire projects and what is the price of it"

        contextual = build_contextual_assist_query(issue, history)
        self.assertIn("live availability pricing", contextual)

        answer = build_company_api_direct_answer(issue, self.chunks, history)
        self.assertIn("highest-priced available home", answer)
        self.assertIn("Project Alpha", answer)
        self.assertNotIn("Project Beta has", answer)
    def test_two_2bhk_flats_are_evaluated_as_a_pair(self):
        issues = [
            "My budget is 40 lakh rupee. I want to buy 2 flats 2BHK.",
            "I want to buy 2 of 2BHK Flats in budget of 40 lakh rupees",
            "I want two 2BHK flats for 40 lakh",
            "I need 2 flats of 2BHK within 40 lakh",
        ]

        for issue in issues:
            with self.subTest(issue=issue):
                answer = build_company_api_direct_answer(issue, self.chunks, [])
                self.assertIn("could not find 2 requested flats within your combined budget", answer)
                self.assertIn("2BHK in Project Beta", answer)
                self.assertIn("2BHK in Project Alpha", answer)
                self.assertIn("Combined estimated base value: INR 4,610,000", answer)
                self.assertNotIn("closest available residential options", answer)
    def test_combined_budget_preserves_one_1bhk_and_one_2bhk(self):
        issue = (
            "My budget is 35 lakh rupees. I want to buy two flats, "
            "one is 1BHK and the other 2BHK. Suggest the best flats."
        )

        answer = build_company_api_direct_answer(issue, self.chunks, [])

        self.assertIn("one 1BHK and one 2BHK", answer)
        self.assertIn("1BHK in Project Gamma", answer)
        self.assertIn("2BHK in Project Beta", answer)
        self.assertIn("Combined estimated starting base value: INR 3,000,000", answer)
        self.assertNotIn("2BHK in Project Alpha", answer)
    def test_property_budget_query_uses_live_flats_not_food_fallback(self):
        issue = "My budget is 25 Lakh rupees can you suggest me flats based on my budget"

        self.assertFalse(is_local_product_feed_recommendation_question(issue))
        contextual = build_contextual_assist_query(issue, [])
        self.assertIn("live residential availability pricing", contextual)

        answer = build_company_api_direct_answer(issue, self.chunks, [])
        self.assertIn("budget of up to INR 25 lakh", answer)
        self.assertIn("Project Beta", answer)
        self.assertNotIn("Project Alpha", answer)
        self.assertNotIn("meals", answer.lower())
        self.assertNotIn("snacks", answer.lower())
    def test_floor_zero_is_displayed_as_ground_floor(self):
        project = self.project_chunk(
            "Project Alpha", 1, "B", 0, "5", 8_000, 3_725, "5BHK"
        )

        answer = build_company_api_direct_answer(
            "What is the highest budget flat and its price?",
            [project],
            [],
        )

        self.assertIn("B wing, ground floor, unit 5", answer)
        self.assertNotIn("B wing, unit 5", answer)
    def test_highly_cost_price_flat_returns_one_highest_value_home(self):
        answer = build_company_api_direct_answer(
            "What is highly cost price Flat in all projects",
            self.chunks,
            [],
        )

        self.assertIn("highest-priced available home", answer)
        self.assertIn("Project Alpha", answer)
        self.assertIn("estimated maximum base value", answer)
        self.assertNotIn("projects currently have live pricing data", answer)
    def test_floor_comparison_paraphrases_do_not_require_all_projects_phrase(self):
        queries = [
            "Which project have more Floors",
            "Which project has the highest number of floors?",
            "Compare projects by floor count",
            "Which project has fewer floors?",
        ]
        for issue in queries:
            with self.subTest(issue=issue):
                self.assertTrue(is_cross_project_floor_comparison_request(issue))
                contextual = build_contextual_assist_query(issue, [])
                self.assertIn("all projects wings total floors comparison", contextual)
    def test_cross_project_floor_comparison_reads_every_project(self):
        alpha = self.project_chunk("Project Alpha", 1, "A", 1, "101", 2_000, 500, "1BHK")
        beta = self.project_chunk("Project Beta", 2, "B", 1, "101", 2_000, 500, "1BHK")
        gamma = self.project_chunk("Project Gamma", 3, "C", 1, "101", 2_000, 500, "1BHK")
        alpha["wings"] = [{"id": 1, "name": "A", "totalFloors": 12}]
        beta["wings"] = [{"id": 2, "name": "B", "totalFloors": 16}]
        gamma["wings"] = [{"id": 3, "name": "C", "totalFloors": 14}]

        answer = build_company_api_direct_answer(
            "Which project has more floors when compared to all projects?",
            [alpha, beta, gamma],
            [],
        )

        self.assertEqual(answer, "Project Beta has the most floors: 16.")
    def test_combined_flat_and_floor_comparison_answers_both_metrics(self):
        alpha = self.project_chunk("Project Alpha", 1, "A", 1, "101", 2_000, 500, "1BHK")
        beta = self.project_chunk("Project Beta", 2, "B", 1, "101", 2_000, 500, "1BHK")
        alpha["wings"] = [{"id": 1, "name": "A", "totalFloors": 12}]
        beta["wings"] = [{"id": 2, "name": "B", "totalFloors": 16}]
        alpha["available_inventory"].append({"unitNumber": "102"})

        answer = build_company_api_direct_answer(
            "Which project has more number of flats and floors?",
            [alpha, beta],
            [],
        )

        self.assertIn("Most currently available flats: Project Alpha has 2.", answer)
        self.assertIn("Most floors: Project Beta has 16.", answer)

    def test_single_wing_project_floor_question_is_direct(self):
        project = self.project_chunk(
            "Vishwajeet Heights", 1, "IRIS", 1, "101", 2_800, 600, "1BHK"
        )
        project["wings"] = [{"id": 1, "name": "IRIS", "totalFloors": 14}]

        answer = build_company_api_direct_answer(
            "How many floors are there in Vishwajeet Heights?",
            [project],
            [],
        )

        self.assertEqual(answer, "Vishwajeet Heights has 14 floors.")
    def test_project_floor_count_does_not_inherit_previous_bhk(self):
        project = self.project_chunk(
            "Project Alpha", 1, "Alpha Wing", 2, "201", 2_900, 900, "2BHK"
        )
        project["wings"] = [
            {"id": 1, "name": "Alpha Wing", "totalFloors": 15},
            {"id": 2, "name": "Beta Wing", "totalFloors": 12},
        ]
        history = [
            {"sender": "customer", "text": "How many 2BHK flats are available?"},
            {"sender": "bot", "text": "There are available 2 BHK units."},
        ]

        answer = build_company_api_direct_answer(
            "In Project Alpha how many total floors are there?",
            [project],
            history,
        )

        self.assertIn("Project Alpha has 2 wings", answer)
        self.assertIn("Alpha Wing: 15 floors", answer)
        self.assertIn("Beta Wing: 12 floors", answer)
        self.assertNotIn("available 2 BHK", answer)
    def test_global_2bhk_count_clears_old_floor_and_project_scope(self):
        history = [
            {"sender": "customer", "text": "Venus A"},
            {"sender": "customer", "text": "Floor 3"},
            {"sender": "bot", "text": "Floor 3 of Venus A has available 2 BHK units."},
        ]
        issue = "How many total flats of 2BHK are there in all projects?"

        answer = build_company_api_direct_answer(issue, self.chunks, history)

        self.assertIn("2 2 BHK units", answer)
        self.assertIn("across 2 projects", answer)
        self.assertIn("Project Alpha: 1 unit", answer)
        self.assertIn("Project Beta: 1 unit", answer)
        self.assertNotIn("floor 3", answer.lower())
    def test_negative_floor_correction_returns_project_context_not_navigation(self):
        answer = build_company_api_direct_answer(
            "I dont want floors, I just want context about Project Beta",
            self.chunks,
            [],
        )
        self.assertIn("verified overview of Project Beta", answer)
        self.assertNotIn("Choose a wing", answer)
        self.assertNotIn("floors", answer.lower())
    def test_browse_projects_is_not_reused_as_affordability_request(self):
        catalogue = [{
            "source_key": "acrobuild-cs-projects",
            "project_names": ["Project Alpha", "Project Beta", "Project Gamma"],
        }]
        history = [
            {"sender": "customer", "text": "Show the most affordable flat"},
            {"sender": "bot", "text": "The most affordable option is in Project Gamma."},
            {"sender": "customer", "text": "Browse projects"},
        ]

        answer = build_company_api_direct_answer(
            "Show me all projects",
            catalogue,
            history,
        )

        self.assertIn("3 projects available to explore", answer)
        self.assertIn("Project Alpha", answer)
        self.assertIn("Project Beta", answer)
        self.assertNotIn("most affordable available home", answer.lower())
    def test_global_recommendation_search_loads_inventory_and_pricing(self):
        issue = "Give me a best affordable flat in your entire projects"
        contextual = build_contextual_assist_query(issue, self.history)

        self.assertIn("live availability pricing", contextual)
        self.assertNotIn("Floor 3", contextual)


if __name__ == "__main__":
    unittest.main()