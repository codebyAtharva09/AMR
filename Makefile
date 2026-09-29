# EdgeSwarm – common tasks.  `make help` lists them.
PY ?= python3

help:            ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | sed 's/:.*##/ -/'

install:         ## install runtime + dev dependencies
	$(PY) -m pip install -r requirements.txt pytest scikit-learn

test:            ## run the full test suite
	$(PY) -m pytest -q

dashboard:       ## start the 3D Command Center on http://127.0.0.1:8000/command-center
	$(PY) main.py --mode dashboard

demo:            ## headless 7-scene demo
	$(PY) main.py --mode edge-demo

benchmark:       ## 30-seed main benchmark (slow)
	$(PY) main.py --mode swarm-benchmark --seeds 30

experiments:     ## all side experiments (outage, stream, handling, PIBT, scaling, safety stress, distributed)
	$(PY) experiments/central_outage.py
	$(PY) experiments/throughput_stream.py
	$(PY) experiments/handling_time.py
	$(PY) experiments/pibt_compare.py
	$(PY) experiments/scaling_large.py
	$(PY) experiments/safety_stress.py
	$(PY) experiments/distributed_check.py

edge-bench:      ## time the per-robot loop on THIS device (run on a Pi / Jetson)
	$(PY) deploy/edge/edge_benchmark.py --robots 10

docker-server:   ## build the dashboard image
	docker build -f deploy/docker/Dockerfile.server -t edgeswarm-dashboard .

docker-edge:     ## build the arm64 robot image
	docker buildx build --platform linux/arm64 -f deploy/docker/Dockerfile.edge -t edgeswarm-edge .

.PHONY: help install test dashboard demo benchmark experiments edge-bench docker-server docker-edge
