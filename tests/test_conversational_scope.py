from graph.haystack_conversation_pipeline import build_deterministic_conversation_answer
from services.ai_agent_service import build_conversational_small_talk_answer


def assert_correct_prabhas_answer(answer):
    assert answer is not None
    assert "Indian film actor" in answer
    assert "Telugu cinema" in answer
    assert "Baahubali" in answer
    assert "Acrobuild technology" not in answer
    assert "software" not in answer.lower()


def test_ai_service_answers_actor_prabhas_correctly():
    assert_correct_prabhas_answer(
        build_conversational_small_talk_answer("Do you know Actor Prabhas?")
    )


def test_haystack_answers_actor_prabhas_without_calling_the_local_model():
    assert_correct_prabhas_answer(
        build_deterministic_conversation_answer("Do you know Actor Prabhas?")
    )