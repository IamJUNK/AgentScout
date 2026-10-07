from agent.fallback import classify_input_fallback, plan_research_fallback

def test_fallback_plan():
    plan = plan_research_fallback("比较 LangGraph 与 CrewAI")
    assert 3 <= len(plan.questions) <= 5
    assert len(set(plan.search_queries)) == len(plan.search_queries)
    assert all("LangGraph" in query for query in plan.search_queries)

def test_job_classification():
    assert classify_input_fallback("AI Agent 实习生：岗位要求 Python，负责评测").input_type == "job_description"

def test_topic_classification():
    assert classify_input_fallback("比较 LangGraph 与 CrewAI").input_type == "research_question"
