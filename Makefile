lint:
	ruff check .
fmt:
	ruff format .
typecheck:
	mypy src/splat360
test:
	pytest tests/unit
clean:
	rm -rf workspace/*
docs:
	echo "docs"
