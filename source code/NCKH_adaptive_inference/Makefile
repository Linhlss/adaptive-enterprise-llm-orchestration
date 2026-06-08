COMPOSE ?= docker compose

Q2_SOURCE_DATASETS ?= systems_evaluation/test_queries_q2_source.json
Q2_DATASET ?= systems_evaluation/test_queries_q2_multidomain.json
Q2_MODEL_DATASET ?= systems_evaluation/test_queries_q2_model_sensitivity.json
Q2_STABILITY_DATASET ?= systems_evaluation/test_queries_q2_stability_subset.json
Q2_ISOLATION_DATASET ?= systems_evaluation/test_queries_q2_isolation.json
Q2_BACKEND ?= vllm

Q2_REPLAY_TRACE_LABEL ?= q2_joint_adaptive_policy_pass
Q2_REPLAY_PREFIX ?= test_queries_q2_joint_replay
Q2_REPLAY_MANIFEST ?= systems_evaluation/test_queries_q2_joint_replay_manifest.json
Q2_REPLAY_STRONG_DATASET ?= systems_evaluation/test_queries_q2_joint_replay_strong_quality.json
Q2_REPLAY_BALANCED_DATASET ?= systems_evaluation/test_queries_q2_joint_replay_balanced.json
Q2_REPLAY_LIGHT_DATASET ?= systems_evaluation/test_queries_q2_joint_replay_light_latency.json

Q2_STABILITY_REPLAY_TRACE_LABEL ?= q2_stability_joint_adaptive_policy_pass
Q2_STABILITY_REPLAY_PREFIX ?= test_queries_q2_stability_joint_replay
Q2_STABILITY_REPLAY_MANIFEST ?= systems_evaluation/test_queries_q2_stability_joint_replay_manifest.json
Q2_STABILITY_REPLAY_STRONG_DATASET ?= systems_evaluation/test_queries_q2_stability_joint_replay_strong_quality.json
Q2_STABILITY_REPLAY_BALANCED_DATASET ?= systems_evaluation/test_queries_q2_stability_joint_replay_balanced.json
Q2_STABILITY_REPLAY_LIGHT_DATASET ?= systems_evaluation/test_queries_q2_stability_joint_replay_light_latency.json

.PHONY: \
	dev-build dev-up dev-shell app-up app-down ps logs bootstrap \
	scaffold-q2-domains scaffold-q2-domains-apply scaffold-q2-domains-refresh \
	build-q2-corpus build-q2-corpus-force audit-q2-corpus \
	prepare-q2-source-pack prepare-q2-benchmark prepare-q2-model-sensitivity prepare-q2-stability-subset prepare-q2-isolation prepare-q2-pack \
	validate-q2-pack validate-q2-model-sensitivity validate-q2-stability-subset validate-q2-isolation \
	validate-q2-content-pack validate-q2-content-model validate-q2-content-stability validate-q2-content-isolation validate-q2-content \
	check-q2-readiness prepare-q2-joint-replay prepare-q2-stability-joint-replay \
	benchmark-q2-routeonly benchmark-q2-e2e benchmark-q2-joint-replay benchmark-q2-model-sensitivity benchmark-q2-stability benchmark-q2-isolation benchmark-q2-pack \
	build-q2-main-table build-q2-model-sensitivity-table build-q2-stability-table build-q2-isolation-table \
	clean-generated-reports clean-python-cache

dev-build:
	$(COMPOSE) build dev

dev-up:
	$(COMPOSE) up -d dev

dev-shell:
	$(COMPOSE) exec dev bash

app-up:
	$(COMPOSE) up -d api ui

app-down:
	$(COMPOSE) down

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f api ui

bootstrap: dev-build dev-up app-up

scaffold-q2-domains:
	$(COMPOSE) exec dev python systems_evaluation/scaffold_q2_domains.py

scaffold-q2-domains-apply:
	$(COMPOSE) exec dev python systems_evaluation/scaffold_q2_domains.py --apply

scaffold-q2-domains-refresh:
	$(COMPOSE) exec dev python systems_evaluation/scaffold_q2_domains.py --apply --force

build-q2-corpus:
	python3 systems_evaluation/build_q2_corpus.py

build-q2-corpus-force:
	python3 systems_evaluation/build_q2_corpus.py --force

audit-q2-corpus:
	python3 systems_evaluation/audit_q2_corpus.py

prepare-q2-source-pack:
	python3 systems_evaluation/generate_q2_source_query_pack.py --output $(Q2_SOURCE_DATASETS)

prepare-q2-benchmark: prepare-q2-source-pack
	$(COMPOSE) exec dev python systems_evaluation/prepare_q2_benchmark_dataset.py --input $(Q2_SOURCE_DATASETS) --output $(Q2_DATASET)

prepare-q2-model-sensitivity: prepare-q2-source-pack
	$(COMPOSE) exec dev python systems_evaluation/prepare_q2_benchmark_dataset.py --input $(Q2_SOURCE_DATASETS) --output $(Q2_MODEL_DATASET) --cases-per-route-domain 6 --id-prefix Q2MODEL

prepare-q2-stability-subset: prepare-q2-source-pack
	$(COMPOSE) exec dev python systems_evaluation/prepare_q2_benchmark_dataset.py --input $(Q2_SOURCE_DATASETS) --output $(Q2_STABILITY_DATASET) --cases-per-route-domain 6 --id-prefix Q2STAB

prepare-q2-isolation:
	$(COMPOSE) exec dev python systems_evaluation/prepare_q2_isolation_dataset.py --output $(Q2_ISOLATION_DATASET)

prepare-q2-pack: prepare-q2-benchmark prepare-q2-model-sensitivity prepare-q2-stability-subset prepare-q2-isolation

validate-q2-pack:
	$(COMPOSE) exec dev python systems_evaluation/validate_q2_benchmark_pack.py --dataset $(Q2_DATASET) --isolation-dataset $(Q2_ISOLATION_DATASET)

validate-q2-model-sensitivity:
	$(COMPOSE) exec dev python systems_evaluation/validate_q2_benchmark_pack.py --dataset $(Q2_MODEL_DATASET) --cases-per-domain 24 --cases-per-route-domain 6 --skip-isolation-check

validate-q2-stability-subset:
	$(COMPOSE) exec dev python systems_evaluation/validate_q2_benchmark_pack.py --dataset $(Q2_STABILITY_DATASET) --cases-per-domain 24 --cases-per-route-domain 6 --skip-isolation-check

validate-q2-isolation:
	$(COMPOSE) exec dev python systems_evaluation/validate_q2_benchmark_pack.py --isolation-only --isolation-dataset $(Q2_ISOLATION_DATASET)

validate-q2-content-pack:
	python3 systems_evaluation/validate_q2_content_semantics.py --dataset $(Q2_DATASET) --strict-absent-keywords --output systems_evaluation/generated_reports/q2_content_validation_main.json

validate-q2-content-model:
	python3 systems_evaluation/validate_q2_content_semantics.py --dataset $(Q2_MODEL_DATASET) --strict-absent-keywords --output systems_evaluation/generated_reports/q2_content_validation_model.json

validate-q2-content-stability:
	python3 systems_evaluation/validate_q2_content_semantics.py --dataset $(Q2_STABILITY_DATASET) --strict-absent-keywords --output systems_evaluation/generated_reports/q2_content_validation_stability.json

validate-q2-content-isolation:
	python3 systems_evaluation/validate_q2_content_semantics.py --dataset $(Q2_ISOLATION_DATASET) --strict-absent-keywords --output systems_evaluation/generated_reports/q2_content_validation_isolation.json

validate-q2-content: validate-q2-content-pack validate-q2-content-model validate-q2-content-stability validate-q2-content-isolation

check-q2-readiness: prepare-q2-source-pack
	$(COMPOSE) exec dev python systems_evaluation/check_q2_readiness.py --input $(Q2_SOURCE_DATASETS)

prepare-q2-joint-replay: validate-q2-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label $(Q2_REPLAY_TRACE_LABEL) --model-class adaptive --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/prepare_q2_controlled_replay.py --dataset $(Q2_DATASET) --trace systems_evaluation/generated_reports/$(Q2_REPLAY_TRACE_LABEL)_predictions.json --output-dir systems_evaluation --prefix $(Q2_REPLAY_PREFIX) --manifest $(Q2_REPLAY_MANIFEST)

prepare-q2-stability-joint-replay: validate-q2-stability-subset
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label $(Q2_STABILITY_REPLAY_TRACE_LABEL) --model-class adaptive --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/prepare_q2_controlled_replay.py --dataset $(Q2_STABILITY_DATASET) --trace systems_evaluation/generated_reports/$(Q2_STABILITY_REPLAY_TRACE_LABEL)_predictions.json --output-dir systems_evaluation --prefix $(Q2_STABILITY_REPLAY_PREFIX) --manifest $(Q2_STABILITY_REPLAY_MANIFEST)

benchmark-q2-routeonly: validate-q2-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_qwen3_14b_awq_routeonly --model-class strong-quality --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_qwen3_8b_awq_routeonly --model-class balanced --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_qwen3_4b_awq_routeonly --model-class light-latency --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_retrieval_routeonly --fixed-route-mode retrieval --model-class balanced --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_general_routeonly --fixed-route-mode general --model-class balanced --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_adaptive_path_only_routeonly --model-class balanced --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label $(Q2_REPLAY_TRACE_LABEL) --model-class adaptive --llm-backend $(Q2_BACKEND) --route-only

benchmark-q2-e2e: validate-q2-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_qwen3_14b_awq_e2e --model-class strong-quality --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_qwen3_8b_awq_e2e --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_qwen3_4b_awq_e2e --model-class light-latency --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_retrieval_e2e --fixed-route-mode retrieval --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_fixed_general_e2e --fixed-route-mode general --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_DATASET) --label q2_adaptive_path_only_e2e --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6

benchmark-q2-joint-replay: prepare-q2-joint-replay
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_REPLAY_STRONG_DATASET) --label q2_joint_adaptive_replay_strong --model-class strong-quality --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_REPLAY_BALANCED_DATASET) --label q2_joint_adaptive_replay_balanced --model-class balanced --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_REPLAY_LIGHT_DATASET) --label q2_joint_adaptive_replay_light --model-class light-latency --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/merge_q2_controlled_replay.py --dataset $(Q2_DATASET) --predictions systems_evaluation/generated_reports/q2_joint_adaptive_replay_strong_predictions.json systems_evaluation/generated_reports/q2_joint_adaptive_replay_balanced_predictions.json systems_evaluation/generated_reports/q2_joint_adaptive_replay_light_predictions.json --output systems_evaluation/generated_reports/q2_joint_adaptive_replay_predictions.json
	$(COMPOSE) exec dev python systems_evaluation/evaluate_answers.py --dataset $(Q2_DATASET) --predictions systems_evaluation/generated_reports/q2_joint_adaptive_replay_predictions.json --label q2_joint_adaptive_replay --output-json systems_evaluation/generated_reports/q2_joint_adaptive_replay_answer_report.json --output-md systems_evaluation/generated_reports/q2_joint_adaptive_replay_answer_report.md

benchmark-q2-model-sensitivity: validate-q2-model-sensitivity
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_MODEL_DATASET) --label q2_model_qwen3_14b_awq_routeonly --model-class strong-quality --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_MODEL_DATASET) --label q2_model_qwen3_8b_awq_routeonly --model-class balanced --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_MODEL_DATASET) --label q2_model_qwen3_4b_awq_routeonly --model-class light-latency --llm-backend $(Q2_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_MODEL_DATASET) --label q2_model_qwen3_14b_awq_e2e --model-class strong-quality --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_MODEL_DATASET) --label q2_model_qwen3_8b_awq_e2e --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_MODEL_DATASET) --label q2_model_qwen3_4b_awq_e2e --model-class light-latency --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6

benchmark-q2-stability: prepare-q2-stability-joint-replay
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_adaptive_path_only_r1 --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_fixed_qwen3_14b_awq_r1 --model-class strong-quality --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_fixed_retrieval_r1 --fixed-route-mode retrieval --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_adaptive_path_only_r2 --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_fixed_qwen3_14b_awq_r2 --model-class strong-quality --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_fixed_retrieval_r2 --fixed-route-mode retrieval --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_adaptive_path_only_r3 --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_fixed_qwen3_14b_awq_r3 --model-class strong-quality --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_DATASET) --label q2_stability_fixed_retrieval_r3 --fixed-route-mode retrieval --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_STRONG_DATASET) --label q2_stability_joint_adaptive_replay_strong_r1 --model-class strong-quality --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_BALANCED_DATASET) --label q2_stability_joint_adaptive_replay_balanced_r1 --model-class balanced --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_LIGHT_DATASET) --label q2_stability_joint_adaptive_replay_light_r1 --model-class light-latency --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/merge_q2_controlled_replay.py --dataset $(Q2_STABILITY_DATASET) --predictions systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_strong_r1_predictions.json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_balanced_r1_predictions.json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_light_r1_predictions.json --output systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r1_predictions.json
	$(COMPOSE) exec dev python systems_evaluation/evaluate_answers.py --dataset $(Q2_STABILITY_DATASET) --predictions systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r1_predictions.json --label q2_stability_joint_adaptive_replay_r1 --output-json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r1_answer_report.json --output-md systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r1_answer_report.md
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_STRONG_DATASET) --label q2_stability_joint_adaptive_replay_strong_r2 --model-class strong-quality --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_BALANCED_DATASET) --label q2_stability_joint_adaptive_replay_balanced_r2 --model-class balanced --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_LIGHT_DATASET) --label q2_stability_joint_adaptive_replay_light_r2 --model-class light-latency --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/merge_q2_controlled_replay.py --dataset $(Q2_STABILITY_DATASET) --predictions systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_strong_r2_predictions.json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_balanced_r2_predictions.json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_light_r2_predictions.json --output systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r2_predictions.json
	$(COMPOSE) exec dev python systems_evaluation/evaluate_answers.py --dataset $(Q2_STABILITY_DATASET) --predictions systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r2_predictions.json --label q2_stability_joint_adaptive_replay_r2 --output-json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r2_answer_report.json --output-md systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r2_answer_report.md
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_STRONG_DATASET) --label q2_stability_joint_adaptive_replay_strong_r3 --model-class strong-quality --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_BALANCED_DATASET) --label q2_stability_joint_adaptive_replay_balanced_r3 --model-class balanced --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_STABILITY_REPLAY_LIGHT_DATASET) --label q2_stability_joint_adaptive_replay_light_r3 --model-class light-latency --llm-backend $(Q2_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/merge_q2_controlled_replay.py --dataset $(Q2_STABILITY_DATASET) --predictions systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_strong_r3_predictions.json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_balanced_r3_predictions.json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_light_r3_predictions.json --output systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r3_predictions.json
	$(COMPOSE) exec dev python systems_evaluation/evaluate_answers.py --dataset $(Q2_STABILITY_DATASET) --predictions systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r3_predictions.json --label q2_stability_joint_adaptive_replay_r3 --output-json systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r3_answer_report.json --output-md systems_evaluation/generated_reports/q2_stability_joint_adaptive_replay_r3_answer_report.md

benchmark-q2-isolation: validate-q2-isolation
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(Q2_ISOLATION_DATASET) --label q2_isolation_e2e --model-class balanced --llm-backend $(Q2_BACKEND) --warmup --warmup-max-tenants 6

build-q2-main-table:
	$(COMPOSE) exec dev python systems_evaluation/build_main_comparison_table.py --dataset $(Q2_DATASET) --output-prefix q2_main_cross_domain_table \
		--row "Fixed Qwen3-14B-AWQ|fixed_model|q2_fixed_qwen3_14b_awq_routeonly_predictions.json|q2_fixed_qwen3_14b_awq_e2e_predictions.json|q2_fixed_qwen3_14b_awq_e2e_answer_report.json" \
		--row "Fixed Qwen3-8B-AWQ|fixed_model|q2_fixed_qwen3_8b_awq_routeonly_predictions.json|q2_fixed_qwen3_8b_awq_e2e_predictions.json|q2_fixed_qwen3_8b_awq_e2e_answer_report.json" \
		--row "Fixed Qwen3-4B-AWQ|fixed_model|q2_fixed_qwen3_4b_awq_routeonly_predictions.json|q2_fixed_qwen3_4b_awq_e2e_predictions.json|q2_fixed_qwen3_4b_awq_e2e_answer_report.json" \
		--row "Fixed retrieval|fixed_path|q2_fixed_retrieval_routeonly_predictions.json|q2_fixed_retrieval_e2e_predictions.json|q2_fixed_retrieval_e2e_answer_report.json" \
		--row "Fixed general|fixed_path|q2_fixed_general_routeonly_predictions.json|q2_fixed_general_e2e_predictions.json|q2_fixed_general_e2e_answer_report.json" \
		--row "Adaptive path-only|adaptive_path|q2_adaptive_path_only_routeonly_predictions.json|q2_adaptive_path_only_e2e_predictions.json|q2_adaptive_path_only_e2e_answer_report.json" \
		--row "Joint adaptive path+model replay|joint_adaptive_replay|$(Q2_REPLAY_TRACE_LABEL)_predictions.json|q2_joint_adaptive_replay_predictions.json|q2_joint_adaptive_replay_answer_report.json"

build-q2-model-sensitivity-table:
	$(COMPOSE) exec dev python systems_evaluation/build_main_comparison_table.py --dataset $(Q2_MODEL_DATASET) --output-prefix q2_model_sensitivity_table \
		--row "Qwen3-14B-AWQ|fixed_model|q2_model_qwen3_14b_awq_routeonly_predictions.json|q2_model_qwen3_14b_awq_e2e_predictions.json|q2_model_qwen3_14b_awq_e2e_answer_report.json" \
		--row "Qwen3-8B-AWQ|fixed_model|q2_model_qwen3_8b_awq_routeonly_predictions.json|q2_model_qwen3_8b_awq_e2e_predictions.json|q2_model_qwen3_8b_awq_e2e_answer_report.json" \
		--row "Qwen3-4B-AWQ|fixed_model|q2_model_qwen3_4b_awq_routeonly_predictions.json|q2_model_qwen3_4b_awq_e2e_predictions.json|q2_model_qwen3_4b_awq_e2e_answer_report.json"

build-q2-stability-table:
	$(COMPOSE) exec dev python systems_evaluation/build_variance_table.py --dataset $(Q2_STABILITY_DATASET) --output-prefix q2_stability_table \
		--row "Adaptive path-only|q2_stability_adaptive_path_only_r1_predictions.json|q2_stability_adaptive_path_only_r1_answer_report.json|q2_stability_adaptive_path_only_r2_predictions.json|q2_stability_adaptive_path_only_r2_answer_report.json|q2_stability_adaptive_path_only_r3_predictions.json|q2_stability_adaptive_path_only_r3_answer_report.json" \
		--row "Joint adaptive path+model replay|q2_stability_joint_adaptive_replay_r1_predictions.json|q2_stability_joint_adaptive_replay_r1_answer_report.json|q2_stability_joint_adaptive_replay_r2_predictions.json|q2_stability_joint_adaptive_replay_r2_answer_report.json|q2_stability_joint_adaptive_replay_r3_predictions.json|q2_stability_joint_adaptive_replay_r3_answer_report.json" \
		--row "Fixed Qwen3-14B-AWQ|q2_stability_fixed_qwen3_14b_awq_r1_predictions.json|q2_stability_fixed_qwen3_14b_awq_r1_answer_report.json|q2_stability_fixed_qwen3_14b_awq_r2_predictions.json|q2_stability_fixed_qwen3_14b_awq_r2_answer_report.json|q2_stability_fixed_qwen3_14b_awq_r3_predictions.json|q2_stability_fixed_qwen3_14b_awq_r3_answer_report.json" \
		--row "Fixed retrieval|q2_stability_fixed_retrieval_r1_predictions.json|q2_stability_fixed_retrieval_r1_answer_report.json|q2_stability_fixed_retrieval_r2_predictions.json|q2_stability_fixed_retrieval_r2_answer_report.json|q2_stability_fixed_retrieval_r3_predictions.json|q2_stability_fixed_retrieval_r3_answer_report.json"

build-q2-isolation-table:
	$(COMPOSE) exec dev python systems_evaluation/build_isolation_summary.py --dataset $(Q2_ISOLATION_DATASET) --predictions systems_evaluation/generated_reports/q2_isolation_e2e_predictions.json --output-prefix q2_isolation_summary

benchmark-q2-pack: prepare-q2-pack validate-q2-pack validate-q2-model-sensitivity validate-q2-stability-subset validate-q2-isolation validate-q2-content benchmark-q2-routeonly benchmark-q2-e2e benchmark-q2-joint-replay benchmark-q2-model-sensitivity benchmark-q2-stability benchmark-q2-isolation build-q2-main-table build-q2-model-sensitivity-table build-q2-stability-table build-q2-isolation-table

clean-generated-reports:
	rm -f systems_evaluation/generated_reports/*.json systems_evaluation/generated_reports/*.md

clean-python-cache:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f \( -name "*.pyc" -o -name ".DS_Store" \) -delete
