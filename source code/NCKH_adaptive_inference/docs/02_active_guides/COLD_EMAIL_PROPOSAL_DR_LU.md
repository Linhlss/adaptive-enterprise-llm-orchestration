# Cold Email Draft for Dr. Qinghua Lu

Subject: Proposal brief: adaptive enterprise LLM orchestration as an AI engineering case study

Dear Dr. Lu,

I hope you are doing well.

I have been reading your work on software engineering for AI, responsible AI engineering, and more recently agent engineering, especially the line of work around responsible AI engineering, reference architectures for foundation-model-based systems and agents, agent design patterns, AgentOps/observability, and evaluation-driven development.

What I found especially valuable is that your work treats these systems not only as model artifacts, but as engineered systems that require architecture, governance, runtime visibility, and evaluation discipline. After reading that line of work, I felt there is still room for more concrete case studies showing how those ideas can be operationalised in shared enterprise LLM settings, where a runtime must decide when to use retrieval, external tools, direct generation, or explicit safe refusal under tenant boundaries and resource constraints, rather than only offering higher-level patterns or process models.

I am currently developing a small systems-and-application project in that direction, tentatively titled **“Adaptive Orchestration for Multi-Domain, Multi-Tenant Enterprise LLM Serving.”** The project is not intended as a new model or a new retrieval method. Rather, I am trying to build a runnable orchestration prototype and a benchmark framework that make route-level decisions explicit, record route traces as runtime evidence, and study controlled path-and-model-tier trade-offs under a practical single-GPU setup.

I thought this project might be relevant to your current research agenda because it could serve as a narrow empirical case for questions that your recent work raises: how architectural decisions are made visible, how responsible behavior is operationalised at runtime, and how foundation-model-based systems can be evaluated beyond isolated prompt-level results. In that sense, I see it less as “another agent application” and more as a small testbed for the serving-policy and runtime-evidence questions that seem important to AI engineering.

I am still at the proposal-and-validation stage rather than the finished-paper stage, so I am writing mainly to ask for guidance. If you had a few minutes, I would be very grateful for your opinion on whether this framing seems methodologically sensible and whether it fits naturally within AI engineering / AgentOps / responsible agent evaluation as you see the field developing.

I have attached a short relevance brief and included the repository link below in case you are open to a quick look:

GitHub repo: https://github.com/Linhlss/Adaptive-LLM-Multi-domain-model.git

The one question I would most value your view on is:

**Does a project like this make sense as a concrete AI engineering case study of the serving-policy layer for foundation-model-based systems, or does it still risk being too close to an implementation exercise?**

Thank you very much for your time and consideration.

Best regards,  
Linh
