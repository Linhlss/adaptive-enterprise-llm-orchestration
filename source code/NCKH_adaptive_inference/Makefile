COMPOSE ?= docker compose

BENCHMARK_SOURCE_DATASET ?= systems_evaluation/test_queries_source.json
BENCHMARK_DATASET ?= systems_evaluation/test_queries_multidomain.json
MODEL_SENSITIVITY_DATASET ?= systems_evaluation/test_queries_model_sensitivity.json
STABILITY_DATASET ?= systems_evaluation/test_queries_stability_subset.json
ISOLATION_DATASET ?= systems_evaluation/test_queries_isolation.json
BENCHMARK_BACKEND ?= vllm

REPLAY_TRACE_LABEL ?= benchmark_joint_adaptive_policy_pass
REPLAY_PREFIX ?= test_queries_benchmark_joint_replay
REPLAY_MANIFEST ?= systems_evaluation/test_queries_benchmark_joint_replay_manifest.json
REPLAY_STRONG_DATASET ?= systems_evaluation/test_queries_benchmark_joint_replay_strong_quality.json
REPLAY_BALANCED_DATASET ?= systems_evaluation/test_queries_benchmark_joint_replay_balanced.json
REPLAY_LIGHT_DATASET ?= systems_evaluation/test_queries_benchmark_joint_replay_light_latency.json

STABILITY_REPLAY_TRACE_LABEL ?= benchmark_stability_joint_adaptive_policy_pass
STABILITY_REPLAY_PREFIX ?= test_queries_benchmark_stability_joint_replay
STABILITY_REPLAY_MANIFEST ?= systems_evaluation/test_queries_benchmark_stability_joint_replay_manifest.json
STABILITY_REPLAY_STRONG_DATASET ?= systems_evaluation/test_queries_benchmark_stability_joint_replay_strong_quality.json
STABILITY_REPLAY_BALANCED_DATASET ?= systems_evaluation/test_queries_benchmark_stability_joint_replay_balanced.json
STABILITY_REPLAY_LIGHT_DATASET ?= systems_evaluation/test_queries_benchmark_stability_joint_replay_light_latency.json

.PHONY: \
	dev-build dev-up dev-shell app-up app-down ps logs bootstrap \
	initialize-benchmark-tenants initialize-benchmark-tenants-apply refresh-benchmark-tenants \
	build-benchmark-corpus build-benchmark-corpus-force audit-benchmark-corpus \
	prepare-source-query-pack prepare-benchmark-core prepare-model-sensitivity-pack prepare-stability-pack prepare-isolation-pack prepare-benchmark-pack \
	validate-benchmark-pack validate-model-sensitivity-pack validate-stability-pack validate-isolation-pack \
	validate-benchmark-content-pack validate-benchmark-content-model validate-benchmark-content-stability validate-benchmark-content-isolation validate-benchmark-content \
	check-benchmark-readiness prepare-joint-replay prepare-stability-joint-replay \
	benchmark-route-policy benchmark-end-to-end benchmark-joint-replay benchmark-model-sensitivity benchmark-stability benchmark-isolation benchmark-full-suite \
	build-main-table build-model-sensitivity-table build-stability-table build-isolation-table \
	build-benchmark-corpus build-benchmark-corpus-force audit-benchmark-corpus \
	prepare-source-query-pack prepare-benchmark-pack prepare-model-sensitivity-pack prepare-stability-pack prepare-isolation-pack \
	validate-benchmark-pack validate-model-sensitivity-pack validate-stability-pack validate-isolation-pack \
	validate-benchmark-content check-benchmark-readiness \
	benchmark-route-policy benchmark-end-to-end benchmark-joint-replay benchmark-model-sensitivity benchmark-stability benchmark-isolation benchmark-full-suite \
	build-main-table build-model-sensitivity-table build-stability-table build-isolation-table \
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

initialize-benchmark-tenants:
	$(COMPOSE) exec dev python systems_evaluation/initialize_benchmark_tenants.py

initialize-benchmark-tenants-apply:
	$(COMPOSE) exec dev python systems_evaluation/initialize_benchmark_tenants.py --apply

refresh-benchmark-tenants:
	$(COMPOSE) exec dev python systems_evaluation/initialize_benchmark_tenants.py --apply --force

build-benchmark-corpus:
	python3 systems_evaluation/build_benchmark_corpus.py

build-benchmark-corpus-force:
	python3 systems_evaluation/build_benchmark_corpus.py --force

audit-benchmark-corpus:
	python3 systems_evaluation/audit_benchmark_corpus.py

prepare-source-query-pack:
	python3 systems_evaluation/build_source_query_pack.py --output $(BENCHMARK_SOURCE_DATASET)

prepare-benchmark-core: prepare-source-query-pack
	$(COMPOSE) exec dev python systems_evaluation/prepare_benchmark_dataset.py --input $(BENCHMARK_SOURCE_DATASET) --output $(BENCHMARK_DATASET)

prepare-model-sensitivity-pack: prepare-source-query-pack
	$(COMPOSE) exec dev python systems_evaluation/prepare_benchmark_dataset.py --input $(BENCHMARK_SOURCE_DATASET) --output $(MODEL_SENSITIVITY_DATASET) --cases-per-route-domain 6 --id-prefix MODEL

prepare-stability-pack: prepare-source-query-pack
	$(COMPOSE) exec dev python systems_evaluation/prepare_benchmark_dataset.py --input $(BENCHMARK_SOURCE_DATASET) --output $(STABILITY_DATASET) --cases-per-route-domain 6 --id-prefix STAB

prepare-isolation-pack:
	$(COMPOSE) exec dev python systems_evaluation/prepare_isolation_dataset.py --output $(ISOLATION_DATASET)

prepare-benchmark-pack: prepare-benchmark-core prepare-model-sensitivity-pack prepare-stability-pack prepare-isolation-pack

validate-benchmark-pack:
	$(COMPOSE) exec dev python systems_evaluation/validate_benchmark_pack.py --dataset $(BENCHMARK_DATASET) --isolation-dataset $(ISOLATION_DATASET)

validate-model-sensitivity-pack:
	$(COMPOSE) exec dev python systems_evaluation/validate_benchmark_pack.py --dataset $(MODEL_SENSITIVITY_DATASET) --cases-per-domain 24 --cases-per-route-domain 6 --skip-isolation-check

validate-stability-pack:
	$(COMPOSE) exec dev python systems_evaluation/validate_benchmark_pack.py --dataset $(STABILITY_DATASET) --cases-per-domain 24 --cases-per-route-domain 6 --skip-isolation-check

validate-isolation-pack:
	$(COMPOSE) exec dev python systems_evaluation/validate_benchmark_pack.py --isolation-only --isolation-dataset $(ISOLATION_DATASET)

validate-benchmark-content-pack:
	python3 systems_evaluation/validate_content_semantics.py --dataset $(BENCHMARK_DATASET) --strict-absent-keywords --output systems_evaluation/generated_reports/benchmark_content_validation_main.json

validate-benchmark-content-model:
	python3 systems_evaluation/validate_content_semantics.py --dataset $(MODEL_SENSITIVITY_DATASET) --strict-absent-keywords --output systems_evaluation/generated_reports/benchmark_content_validation_model.json

validate-benchmark-content-stability:
	python3 systems_evaluation/validate_content_semantics.py --dataset $(STABILITY_DATASET) --strict-absent-keywords --output systems_evaluation/generated_reports/benchmark_content_validation_stability.json

validate-benchmark-content-isolation:
	python3 systems_evaluation/validate_content_semantics.py --dataset $(ISOLATION_DATASET) --strict-absent-keywords --output systems_evaluation/generated_reports/benchmark_content_validation_isolation.json

validate-benchmark-content: validate-benchmark-content-pack validate-benchmark-content-model validate-benchmark-content-stability validate-benchmark-content-isolation

check-benchmark-readiness: prepare-source-query-pack
	$(COMPOSE) exec dev python systems_evaluation/check_benchmark_readiness.py --input $(BENCHMARK_SOURCE_DATASET)

prepare-joint-replay: validate-benchmark-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label $(REPLAY_TRACE_LABEL) --model-class adaptive --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/prepare_controlled_replay.py --dataset $(BENCHMARK_DATASET) --trace systems_evaluation/generated_reports/$(REPLAY_TRACE_LABEL)_predictions.json --output-dir systems_evaluation --prefix $(REPLAY_PREFIX) --manifest $(REPLAY_MANIFEST)

prepare-stability-joint-replay: validate-stability-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label $(STABILITY_REPLAY_TRACE_LABEL) --model-class adaptive --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/prepare_controlled_replay.py --dataset $(STABILITY_DATASET) --trace systems_evaluation/generated_reports/$(STABILITY_REPLAY_TRACE_LABEL)_predictions.json --output-dir systems_evaluation --prefix $(STABILITY_REPLAY_PREFIX) --manifest $(STABILITY_REPLAY_MANIFEST)

benchmark-route-policy: validate-benchmark-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_qwen3_14b_awq_routeonly --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_qwen3_8b_awq_routeonly --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_qwen3_4b_awq_routeonly --model-class light-latency --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_retrieval_routeonly --fixed-route-mode retrieval --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_general_routeonly --fixed-route-mode general --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_adaptive_path_only_routeonly --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label $(REPLAY_TRACE_LABEL) --model-class adaptive --llm-backend $(BENCHMARK_BACKEND) --route-only

benchmark-end-to-end: validate-benchmark-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_qwen3_14b_awq_e2e --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_qwen3_8b_awq_e2e --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_qwen3_4b_awq_e2e --model-class light-latency --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_retrieval_e2e --fixed-route-mode retrieval --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_fixed_general_e2e --fixed-route-mode general --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(BENCHMARK_DATASET) --label benchmark_adaptive_path_only_e2e --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6

benchmark-joint-replay: prepare-joint-replay
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(REPLAY_STRONG_DATASET) --label benchmark_joint_adaptive_replay_strong --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(REPLAY_BALANCED_DATASET) --label benchmark_joint_adaptive_replay_balanced --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(REPLAY_LIGHT_DATASET) --label benchmark_joint_adaptive_replay_light --model-class light-latency --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/merge_controlled_replay.py --dataset $(BENCHMARK_DATASET) --predictions systems_evaluation/generated_reports/benchmark_joint_adaptive_replay_strong_predictions.json systems_evaluation/generated_reports/benchmark_joint_adaptive_replay_balanced_predictions.json systems_evaluation/generated_reports/benchmark_joint_adaptive_replay_light_predictions.json --output systems_evaluation/generated_reports/benchmark_joint_adaptive_replay_predictions.json
	$(COMPOSE) exec dev python systems_evaluation/evaluate_answers.py --dataset $(BENCHMARK_DATASET) --predictions systems_evaluation/generated_reports/benchmark_joint_adaptive_replay_predictions.json --label benchmark_joint_adaptive_replay --output-json systems_evaluation/generated_reports/benchmark_joint_adaptive_replay_answer_report.json --output-md systems_evaluation/generated_reports/benchmark_joint_adaptive_replay_answer_report.md

benchmark-model-sensitivity: validate-model-sensitivity-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(MODEL_SENSITIVITY_DATASET) --label benchmark_model_qwen3_14b_awq_routeonly --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(MODEL_SENSITIVITY_DATASET) --label benchmark_model_qwen3_8b_awq_routeonly --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(MODEL_SENSITIVITY_DATASET) --label benchmark_model_qwen3_4b_awq_routeonly --model-class light-latency --llm-backend $(BENCHMARK_BACKEND) --route-only
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(MODEL_SENSITIVITY_DATASET) --label benchmark_model_qwen3_14b_awq_e2e --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(MODEL_SENSITIVITY_DATASET) --label benchmark_model_qwen3_8b_awq_e2e --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(MODEL_SENSITIVITY_DATASET) --label benchmark_model_qwen3_4b_awq_e2e --model-class light-latency --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6

benchmark-stability: prepare-stability-joint-replay
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_adaptive_path_only_r1 --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_fixed_qwen3_14b_awq_r1 --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_fixed_retrieval_r1 --fixed-route-mode retrieval --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_adaptive_path_only_r2 --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_fixed_qwen3_14b_awq_r2 --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_fixed_retrieval_r2 --fixed-route-mode retrieval --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_adaptive_path_only_r3 --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_fixed_qwen3_14b_awq_r3 --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_DATASET) --label benchmark_stability_fixed_retrieval_r3 --fixed-route-mode retrieval --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_STRONG_DATASET) --label benchmark_stability_joint_adaptive_replay_strong_r1 --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_BALANCED_DATASET) --label benchmark_stability_joint_adaptive_replay_balanced_r1 --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_LIGHT_DATASET) --label benchmark_stability_joint_adaptive_replay_light_r1 --model-class light-latency --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/merge_controlled_replay.py --dataset $(STABILITY_DATASET) --predictions systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_strong_r1_predictions.json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_balanced_r1_predictions.json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_light_r1_predictions.json --output systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r1_predictions.json
	$(COMPOSE) exec dev python systems_evaluation/evaluate_answers.py --dataset $(STABILITY_DATASET) --predictions systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r1_predictions.json --label benchmark_stability_joint_adaptive_replay_r1 --output-json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r1_answer_report.json --output-md systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r1_answer_report.md
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_STRONG_DATASET) --label benchmark_stability_joint_adaptive_replay_strong_r2 --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_BALANCED_DATASET) --label benchmark_stability_joint_adaptive_replay_balanced_r2 --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_LIGHT_DATASET) --label benchmark_stability_joint_adaptive_replay_light_r2 --model-class light-latency --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/merge_controlled_replay.py --dataset $(STABILITY_DATASET) --predictions systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_strong_r2_predictions.json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_balanced_r2_predictions.json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_light_r2_predictions.json --output systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r2_predictions.json
	$(COMPOSE) exec dev python systems_evaluation/evaluate_answers.py --dataset $(STABILITY_DATASET) --predictions systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r2_predictions.json --label benchmark_stability_joint_adaptive_replay_r2 --output-json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r2_answer_report.json --output-md systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r2_answer_report.md
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_STRONG_DATASET) --label benchmark_stability_joint_adaptive_replay_strong_r3 --model-class strong-quality --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_BALANCED_DATASET) --label benchmark_stability_joint_adaptive_replay_balanced_r3 --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(STABILITY_REPLAY_LIGHT_DATASET) --label benchmark_stability_joint_adaptive_replay_light_r3 --model-class light-latency --llm-backend $(BENCHMARK_BACKEND) --replay-route-from-dataset --warmup --warmup-max-tenants 6
	$(COMPOSE) exec dev python systems_evaluation/merge_controlled_replay.py --dataset $(STABILITY_DATASET) --predictions systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_strong_r3_predictions.json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_balanced_r3_predictions.json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_light_r3_predictions.json --output systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r3_predictions.json
	$(COMPOSE) exec dev python systems_evaluation/evaluate_answers.py --dataset $(STABILITY_DATASET) --predictions systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r3_predictions.json --label benchmark_stability_joint_adaptive_replay_r3 --output-json systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r3_answer_report.json --output-md systems_evaluation/generated_reports/benchmark_stability_joint_adaptive_replay_r3_answer_report.md

benchmark-isolation: validate-isolation-pack
	$(COMPOSE) exec dev python systems_evaluation/run_real_benchmark.py --dataset $(ISOLATION_DATASET) --label benchmark_isolation_e2e --model-class balanced --llm-backend $(BENCHMARK_BACKEND) --warmup --warmup-max-tenants 6

build-main-table:
	$(COMPOSE) exec dev python systems_evaluation/build_main_comparison_table.py --dataset $(BENCHMARK_DATASET) --output-prefix benchmark_main_cross_domain_table \
		--row "Fixed Qwen3-14B-AWQ|fixed_model|benchmark_fixed_qwen3_14b_awq_routeonly_predictions.json|benchmark_fixed_qwen3_14b_awq_e2e_predictions.json|benchmark_fixed_qwen3_14b_awq_e2e_answer_report.json" \
		--row "Fixed Qwen3-8B-AWQ|fixed_model|benchmark_fixed_qwen3_8b_awq_routeonly_predictions.json|benchmark_fixed_qwen3_8b_awq_e2e_predictions.json|benchmark_fixed_qwen3_8b_awq_e2e_answer_report.json" \
		--row "Fixed Qwen3-4B-AWQ|fixed_model|benchmark_fixed_qwen3_4b_awq_routeonly_predictions.json|benchmark_fixed_qwen3_4b_awq_e2e_predictions.json|benchmark_fixed_qwen3_4b_awq_e2e_answer_report.json" \
		--row "Fixed retrieval|fixed_path|benchmark_fixed_retrieval_routeonly_predictions.json|benchmark_fixed_retrieval_e2e_predictions.json|benchmark_fixed_retrieval_e2e_answer_report.json" \
		--row "Fixed general|fixed_path|benchmark_fixed_general_routeonly_predictions.json|benchmark_fixed_general_e2e_predictions.json|benchmark_fixed_general_e2e_answer_report.json" \
		--row "Adaptive path-only|adaptive_path|benchmark_adaptive_path_only_routeonly_predictions.json|benchmark_adaptive_path_only_e2e_predictions.json|benchmark_adaptive_path_only_e2e_answer_report.json" \
		--row "Joint adaptive path+model replay|joint_adaptive_replay|$(REPLAY_TRACE_LABEL)_predictions.json|benchmark_joint_adaptive_replay_predictions.json|benchmark_joint_adaptive_replay_answer_report.json"

build-model-sensitivity-table:
	$(COMPOSE) exec dev python systems_evaluation/build_main_comparison_table.py --dataset $(MODEL_SENSITIVITY_DATASET) --output-prefix benchmark_model_sensitivity_table \
		--row "Qwen3-14B-AWQ|fixed_model|benchmark_model_qwen3_14b_awq_routeonly_predictions.json|benchmark_model_qwen3_14b_awq_e2e_predictions.json|benchmark_model_qwen3_14b_awq_e2e_answer_report.json" \
		--row "Qwen3-8B-AWQ|fixed_model|benchmark_model_qwen3_8b_awq_routeonly_predictions.json|benchmark_model_qwen3_8b_awq_e2e_predictions.json|benchmark_model_qwen3_8b_awq_e2e_answer_report.json" \
		--row "Qwen3-4B-AWQ|fixed_model|benchmark_model_qwen3_4b_awq_routeonly_predictions.json|benchmark_model_qwen3_4b_awq_e2e_predictions.json|benchmark_model_qwen3_4b_awq_e2e_answer_report.json"

build-stability-table:
	$(COMPOSE) exec dev python systems_evaluation/build_variance_table.py --dataset $(STABILITY_DATASET) --output-prefix benchmark_stability_table \
		--row "Adaptive path-only|benchmark_stability_adaptive_path_only_r1_predictions.json|benchmark_stability_adaptive_path_only_r1_answer_report.json|benchmark_stability_adaptive_path_only_r2_predictions.json|benchmark_stability_adaptive_path_only_r2_answer_report.json|benchmark_stability_adaptive_path_only_r3_predictions.json|benchmark_stability_adaptive_path_only_r3_answer_report.json" \
		--row "Joint adaptive path+model replay|benchmark_stability_joint_adaptive_replay_r1_predictions.json|benchmark_stability_joint_adaptive_replay_r1_answer_report.json|benchmark_stability_joint_adaptive_replay_r2_predictions.json|benchmark_stability_joint_adaptive_replay_r2_answer_report.json|benchmark_stability_joint_adaptive_replay_r3_predictions.json|benchmark_stability_joint_adaptive_replay_r3_answer_report.json" \
		--row "Fixed Qwen3-14B-AWQ|benchmark_stability_fixed_qwen3_14b_awq_r1_predictions.json|benchmark_stability_fixed_qwen3_14b_awq_r1_answer_report.json|benchmark_stability_fixed_qwen3_14b_awq_r2_predictions.json|benchmark_stability_fixed_qwen3_14b_awq_r2_answer_report.json|benchmark_stability_fixed_qwen3_14b_awq_r3_predictions.json|benchmark_stability_fixed_qwen3_14b_awq_r3_answer_report.json" \
		--row "Fixed retrieval|benchmark_stability_fixed_retrieval_r1_predictions.json|benchmark_stability_fixed_retrieval_r1_answer_report.json|benchmark_stability_fixed_retrieval_r2_predictions.json|benchmark_stability_fixed_retrieval_r2_answer_report.json|benchmark_stability_fixed_retrieval_r3_predictions.json|benchmark_stability_fixed_retrieval_r3_answer_report.json"

build-isolation-table:
	$(COMPOSE) exec dev python systems_evaluation/build_isolation_summary.py --dataset $(ISOLATION_DATASET) --predictions systems_evaluation/generated_reports/benchmark_isolation_e2e_predictions.json --output-prefix benchmark_isolation_summary

benchmark-full-suite: prepare-benchmark-pack validate-benchmark-pack validate-model-sensitivity-pack validate-stability-pack validate-isolation-pack validate-benchmark-content benchmark-route-policy benchmark-end-to-end benchmark-joint-replay benchmark-model-sensitivity benchmark-stability benchmark-isolation build-main-table build-model-sensitivity-table build-stability-table build-isolation-table

clean-generated-reports:
	rm -f systems_evaluation/generated_reports/*.json systems_evaluation/generated_reports/*.md

clean-python-cache:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	find . -type f \( -name "*.pyc" -o -name ".DS_Store" \) -delete
