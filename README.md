# Implement Search Engines Assessment

## Project Overview

The Implement Search Engines Assessment demonstrates how to build a reliable, validated, and access-controlled search tool gateway for an AI agent. The project uses a local knowledge fixture to retrieve relevant documents, rank results, and return source URLs and cited snippets.

The implementation focuses on structured tool contracts, strict input validation, authorization, search quality, and operational reliability.

## Objectives

- Define a structured search tool contract and registry.
- Validate search inputs and outputs using Pydantic.
- Search a local knowledge base and rank matching documents.
- Support query normalization, domain filters, and freshness preferences.
- Return relevant results with source URLs, snippets, scores, and citations.
- Enforce role-based authorization and read-only tool access.
- Demonstrate bounded retries, provider timeouts, rate limiting, and idempotency.
- Capture structured execution events and JSON evidence artifacts.

## Project Structure

```text
Implement_Search_Engines_Assessment/
├── src/
│   ├── contracts.py
│   ├── gateway.py
│   ├── registry.py
│   ├── reliability.py
│   ├── schemas.py
│   └── search_engine.py
├── tests/
├── schemas/
│   ├── search_input.json
│   └── search_output.json
├── workspace/
│   └── knowledge.json
├── traces/
├── evidence/
│   ├── generate_evidence.py
│   ├── task1_search_results.json
│   ├── task2_gateway_execution.json
│   ├── task3_validation.json
│   ├── task4_retry_evidence.json
│   ├── task5_rate_limit_evidence.json
│   └── task6_idempotency_evidence.json
├── requirements.txt
├── .gitignore
└── README.md
```

## Technology Stack

- Python 3.13
- Pydantic 2.x
- Pytest
- JSON-based knowledge fixtures
- Python standard library for ranking, retries, timeouts, rate limiting, and caching

## Implementation Details

### 1. Search Engine

The search engine normalizes queries, tokenizes searchable text, and calculates relevance scores using title and content matches. Title matches receive greater weight than content matches. Results are sorted by relevance, filtered by domain and freshness preferences, and limited to the requested result count.

Each result contains a title, URL, snippet, source domain, and relevance score. The response also includes a result count and citation URLs.

### 2. Contracts and Validation

Pydantic models validate search requests and response structures. The input contract restricts query length, result limits, freshness values, and domain filters. Unsupported input fields are rejected.

### 3. Tool Gateway and Authorization

The `dispatch()` function validates the tool-call envelope, checks the registered tool and caller's role, and enforces the read-only access policy before invoking the search provider. Structured results include execution status, errors, suggested next actions, and trace events.

### 4. Reliability

The reliability module provides bounded retry attempts, provider timeout handling, sliding-window rate limiting, and an idempotency store. These mechanisms help manage transient failures, excessive requests, and repeated equivalent calls.

### 5. Evidence and Testing

The evidence generator creates JSON artifacts covering search results, gateway execution, invalid-input handling, transient provider retries, rate limiting, and idempotency.

The reported full test-suite result is **47 passed**. Rerun the tests before submission to confirm the current project state.

## Setup Instructions

Open a terminal in the project directory and activate the virtual environment:

```cmd
.venv\Scripts\activate
```

Install dependencies:

```cmd
python -m pip install -r requirements.txt
```

Run the complete test suite:

```cmd
python -m pytest -q
```

Run a search through the gateway:

```cmd
python -m src.gateway "Python documentation"
```

Generate evidence files:

```cmd
python evidence\generate_evidence.py
```

## Expected Outcomes

A successful search returns structured, ranked results with source citations. Invalid requests are rejected, unauthorized requests are denied, and configured reliability controls handle transient provider failures, timeouts, rate limits, and repeated calls.

## Reflection

This project helped me understand how a search capability can be implemented as a structured tool for an AI agent rather than as an isolated search function. I learned that reliable tool execution requires more than retrieving relevant information: the system must validate inputs, enforce access policies, return predictable output, and communicate failures clearly.

Implementing the search engine gave me practical experience with query normalization, tokenization, relevance scoring, ranking, freshness filtering, and domain restrictions. Giving title matches greater weight than content matches provided a simple, explainable ranking strategy suitable for a local knowledge base.

The gateway implementation reinforced the importance of separating the tool contract, registry, validation, authorization, provider execution, and reliability controls. Pydantic helped enforce request and response structures, while the registry defined the available tool and its permitted access. The gateway also demonstrated why authorization should happen before provider execution.

I explored reliability mechanisms including bounded retries, timeout handling, sliding-window rate limiting, and idempotency. These features address different problems and must be tested independently. For example, retries can help recover from transient connection failures, while rate limiting controls request frequency and idempotency avoids repeating successful equivalent work.

The automated tests and JSON evidence generator made the implementation easier to verify. They provided repeatable checks for expected behavior and created artifacts that can be inspected during review. The reported test suite completed with 47 passing tests.

One limitation is that the search provider uses a small local JSON fixture rather than a live search API. The ranking method is also intentionally simple and would need evaluation against a larger, more diverse collection. Future improvements could include a real search provider adapter, richer ranking signals, improved concurrency controls, and more detailed operational metrics.

Overall, this assessment strengthened my understanding of building search tools that are structured, testable, secure, and suitable for integration into agent workflows.
