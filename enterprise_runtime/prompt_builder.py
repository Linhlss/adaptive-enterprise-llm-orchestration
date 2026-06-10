from __future__ import annotations

import re

from llama_index.core import PromptTemplate

from enterprise_runtime.models import TenantProfile


def build_augmented_prompt(
    profile: TenantProfile,
    question: str,
    memory_text: str,
    retrieved_context: str,
    tool_result: str = "",
) -> str:
    template = PromptTemplate(
        """
You are the senior AI assistant for a multi-tenant agentic RAG system.

[TENANT PROFILE]
- Display name: {display_name}
- Persona: {persona}
- Language hint: {language_hint}

[LANGUAGE RULES]
1. Detect the language of the current question.
2. Answer in that same language.
3. Do not switch to English unless the user is already using English.

[CONTENT RULES]
1. Prioritize factual evidence from [TOOL RESULT] and [RETRIEVED CONTEXT].
2. Do not use placeholders such as [insert topic here].
3. If the evidence is incomplete, state exactly what is missing.
4. Keep the answer structured, clear, and professional.
5. Do not invent sources.

[CONVERSATION HISTORY]
{memory_text}

[TOOL RESULT]
{tool_result}

[RETRIEVED CONTEXT]
{retrieved_context}

[CURRENT QUESTION]
{question}

[FINAL INSTRUCTION]
Answer immediately in the same language as the question. If data is missing, say exactly what is missing.
""".strip()
    )
    return template.format(
        display_name=profile.display_name,
        persona=profile.persona,
        language_hint=profile.language_hint,
        memory_text=memory_text or "No conversation history.",
        tool_result=tool_result or "None.",
        retrieved_context=retrieved_context or "None.",
        question=question,
    )


def build_query_rewrite_prompt(
    profile: TenantProfile,
    question: str,
    memory_text: str,
) -> str:
    template = PromptTemplate(
        """
You are performing the QUERY REWRITE step for a multi-domain internal document assistant.

[TENANT PROFILE]
- Display name: {display_name}
- Persona: {persona}

[CONVERSATION HISTORY]
{memory_text}

[ORIGINAL QUESTION]
{question}

[GOAL]
Rewrite the query concisely so retrieval works better.
- Preserve the original meaning.
- If the question is already clear, return something very close to the original wording.
- If the question contains vague references such as "it" or "that", resolve them from the conversation history.
- Preserve important document keywords, file names, policies, procedures, SOPs, checklists, HR/compliance/procurement terms, and domain-specific terminology when present.
- Do not answer the question.
- Output exactly one rewritten query line and nothing else.
""".strip()
    )
    return template.format(
        display_name=profile.display_name,
        persona=profile.persona,
        memory_text=memory_text or "No conversation history.",
        question=question,
    )


def build_rag_draft_prompt(
    profile: TenantProfile,
    question: str,
    rewritten_query: str,
    memory_text: str,
    retrieved_context: str,
) -> str:
    template = PromptTemplate(
        """
Answer the user directly using the retrieved context below.

[TENANT PROFILE]
- Display name: {display_name}
- Persona: {persona}
- Language hint: {language_hint}

[CONVERSATION HISTORY]
{memory_text}

[ORIGINAL QUESTION]
{question}

[REWRITTEN QUERY]
{rewritten_query}

[RETRIEVED CONTEXT]
{retrieved_context}

[REQUIREMENTS]
- Draft the answer primarily from the retrieved context.
- If the context is insufficient, state what evidence is missing.
- If the question requests another tenant's private data and the context does not prove access, refuse clearly and state that cross-tenant access is not allowed.
- Do not invent regulations, numbers, or sources.
- Answer in the user's language.
- Do not mention prompt chaining, draft stages, reasoning traces, or internal system steps.
- Write as if this is the final user-facing answer, while preserving important phrasing from the question when helpful.
- Prioritize factual correctness and grounding over stylistic polish.
""".strip()
    )
    return template.format(
        display_name=profile.display_name,
        persona=profile.persona,
        language_hint=profile.language_hint,
        memory_text=memory_text or "No conversation history.",
        question=question,
        rewritten_query=rewritten_query,
        retrieved_context=retrieved_context or "No retrieved context.",
    )


def build_general_draft_prompt(
    profile: TenantProfile,
    question: str,
    memory_text: str,
) -> str:
    template = PromptTemplate(
        """
Answer the user directly as a helpful and natural assistant.

[TENANT PROFILE]
- Display name: {display_name}
- Persona: {persona}
- Language hint: {language_hint}

[CONVERSATION HISTORY]
{memory_text}

[QUESTION]
{question}

[REQUIREMENTS]
- Respond directly, helpfully, and in the user's language.
- Do not mention prompts, draft stages, internal workflows, or that you are "drafting an answer."
- If the user asks you to remember, repeat, or confirm a string in the current conversation, do it briefly and literally.
- If the user asks you to remember a string, repeat the exact string and briefly confirm that you will use it within the current conversation.
- Do not turn a memory request into a query rewrite request or a request for extra context.
- Do not pretend that you used internal documents if you did not.
- If the user actually needs internal data, briefly say that they should specify the document or topic.
- If the question requests another tenant's data, files, or conversation memory, refuse clearly and state that cross-tenant access is not allowed.
- If the information is not present in the current conversation memory, say so explicitly instead of guessing.
- Do not append a "Sources used" section unless sources were genuinely used.
- Stay close to the user's key wording when that improves clarity.
""".strip()
    )
    return template.format(
        display_name=profile.display_name,
        persona=profile.persona,
        language_hint=profile.language_hint,
        memory_text=memory_text or "No conversation history.",
        question=question,
    )


def build_tool_synthesis_prompt(
    profile: TenantProfile,
    question: str,
    tool_result: str,
    memory_text: str,
) -> str:
    template = PromptTemplate(
        """
You are in the TOOL SYNTHESIS step.

[TENANT PROFILE]
- Display name: {display_name}
- Persona: {persona}
- Language hint: {language_hint}

[CONVERSATION HISTORY]
{memory_text}

[QUESTION]
{question}

[RAW TOOL RESULT]
{tool_result}

[REQUIREMENTS]
- Summarize the tool result into a short, clear answer.
- Do not add information beyond the tool result.
- Preserve the language of the user's question.
- If the tool result is a cross-tenant access refusal, preserve that refusal and do not expand it into data content.
""".strip()
    )
    return template.format(
        display_name=profile.display_name,
        persona=profile.persona,
        language_hint=profile.language_hint,
        memory_text=memory_text or "No conversation history.",
        question=question,
        tool_result=tool_result or "No tool data.",
    )


def build_verification_prompt(
    question: str,
    draft_answer: str,
    retrieved_context: str,
) -> str:
    template = PromptTemplate(
        """
You are in the VERIFY ANSWER step.

[QUESTION]
{question}

[DRAFT]
{draft_answer}

[RETRIEVED CONTEXT]
{retrieved_context}

[REQUIREMENTS]
Check the draft against the context and produce a corrected answer:
- Keep only claims that can be supported by the context.
- Remove or soften claims that are not clearly supported.
- If the context is insufficient, state the data limitation explicitly.
- Do not add new information beyond the context.
- Return only the corrected answer, without explaining the verification process.
- Preserve the language of the original question.
""".strip()
    )
    return template.format(
        question=question,
        draft_answer=draft_answer,
        retrieved_context=retrieved_context or "No retrieved context.",
    )


def build_style_rewrite_prompt(
    profile: TenantProfile,
    question: str,
    answer_text: str,
    use_internal_context: bool,
) -> str:
    style_note = (
        "Because this answer uses internal documents, prioritize clarity, grounded evidence, and explicit acknowledgment of missing data."
        if use_internal_context
        else "Because this is a general answer, keep it concise, natural, and direct."
    )

    template = PromptTemplate(
        """
You are in the STYLE REWRITE step.

[TENANT PROFILE]
- Display name: {display_name}
- Persona: {persona}
- Language hint: {language_hint}

[ORIGINAL QUESTION]
{question}

[ANSWER TO REWRITE]
{answer_text}

[STYLE GUIDANCE]
{style_note}

[REQUIREMENTS]
- Rewrite the answer so it is clear, natural, and professional.
- Do not add new information.
- Preserve the original meaning.
- Answer in the same language as the original question.
- Do not begin with phrases such as "Here is the rewritten answer" or any process explanation.
- Return only the final answer text.
""".strip()
    )
    return template.format(
        display_name=profile.display_name,
        persona=profile.persona,
        language_hint=profile.language_hint,
        question=question,
        answer_text=answer_text,
        style_note=style_note,
    )


def append_sources(answer: str, sources: list[str], show_sources: bool) -> str:
    if not show_sources or not sources:
        return answer
    unique_sources = list(dict.fromkeys(sources))
    return answer.strip() + "\n\nSources used:\n- " + "\n- ".join(unique_sources)


def build_general_prompt(
    profile: TenantProfile,
    question: str,
    memory_text: str,
) -> str:
    template = PromptTemplate(
        """
You are a friendly and accurate AI assistant for a multi-tenant agentic RAG system.

[TENANT PROFILE]
- Display name: {display_name}
- Persona: {persona}
- Language hint: {language_hint}

[RULES]
1. Respond in the user's language.
2. For general-knowledge or conversational questions, do not pretend that internal data was used if RAG was not used.
3. If the question needs internal document data that is not available, ask the user to specify the document or topic.
4. Keep the answer concise, clear, and useful.

[CONVERSATION HISTORY]
{memory_text}

[CURRENT QUESTION]
{question}

[FINAL INSTRUCTION]
Answer directly in the language of the current question.
""".strip()
    )
    return template.format(
        display_name=profile.display_name,
        persona=profile.persona,
        language_hint=profile.language_hint,
        memory_text=memory_text or "No conversation history.",
        question=question,
    )


def _looks_like_english(question: str) -> bool:
    q = (question or "").lower()
    return bool(re.search(r"\b(how|give me|step-by-step|campus|security|server|script|illegal)\b", q))


def build_out_of_scope_answer(question: str) -> str:
    q = (question or "").lower()
    if _looks_like_english(question):
        return (
            "I cannot assist with illegal, harmful, or unsafe instructions. "
            "I do not support requests like this, but I can help with a safe alternative such as security awareness, prevention, or policy-compliant guidance."
        )

    if any(term in q for term in ["password", "phishing", "credential theft", "email scam"]):
        return (
            "I refuse to help with this request because it involves phishing, password theft, or other unauthorized activity. "
            "If useful, I can help with phishing awareness and safe account-protection guidance."
        )

    if any(term in q for term in ["bomb", "weapon", "drug synthesis"]):
        return (
            "I refuse to help with this request because it is dangerous, illegal, and unsafe, such as building weapons or producing prohibited substances. "
            "If useful, I can provide safety-oriented or harm-prevention information instead."
        )

    return (
        "I refuse to help with this request because it is illegal, dangerous, or unsafe. "
        "You can instead ask about documents, policies, procedures, internal files/tables, or other safe and lawful topics."
    )


def build_prompt(query, docs, history=None):
    context = "\n\n".join([d["content"] for d in docs])

    history_text = ""
    if history:
        history_text = "\n".join(
            [f"User: {h['query']}\nBot: {h['response']}" for h in history]
        )

    return f"""
History:
{history_text}

Context:
{context}

Question:
{query}

Answer:
"""
