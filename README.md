# AMD Hackathon - Agent Workflow Project

This repository contains our project for the AMD Hackathon.

## Project idea

We are building an AI agent workflow that can process technical or incident reports, extract useful information, reason over the content, and generate structured outputs for decision-making.

The goal is not only to call an LLM, but to build a clear workflow:
input document → extraction → analysis → agent reasoning → structured report → demo/dashboard.

## Team roles

- Step 1: Document/input processing
- Step 2: Backend/API + evaluation
- Step 3: Agent / Workflow layer
- Step 4: Frontend / demo / pitch / storytelling

## Repository structure

```text
docs/              Documentation, idea, architecture, demo script
data/samples/      Sample reports and test documents
backend/           Backend API and services
agent-workflow/    Agent orchestration and workflow logic
frontend/          Dashboard and demo interface
evaluation/        Evaluation, scoring, metrics and test cases