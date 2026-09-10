# DeepResearch Survey Report

This report synthesizes insights from recent outstanding papers on **DeepResearch**. It surveys the current landscape, and documents the **core objectives**, **primary tasks**, **key workflow**, **major bottlenecks**, and **optimization strategies** in this emerging field.

---

## 1. Definition, Characteristics, and Core Tasks

### Definition

**DeepResearch** refers to the process of **integrating information from diverse, high-volume sources**, performing **comprehensive reasoning** across these sources, and producing either a **final answer** or a **full research report**.

### Key Characteristics

- **High search intensity** – The model must flexibly use various search tools (e.g., local databases, specialized APIs, web search) to retrieve relevant information as needed.
- **High reasoning intensity** – The model must conduct deep reasoning over retrieved, often fragmented, information to synthesize coherent outputs.

### Core Tasks

Currently, DeepResearch focuses on two primary task types:

| Task Type              | Description                                                  |
| ---------------------- | ------------------------------------------------------------ |
| **Question Answering** | Retrieve information relevant to a specific query and produce an **accurate, factual answer**. |
| **Report Generation**  | Retrieve domain-specific information, synthesize it, and generate a **complete, comprehensive, and precise** report that meets user requirements. |

---

## 2. Core Workflow of DeepResearch

The typical pipeline consists of four main stages:

1. **Problem Formulation**  
   – Initial research directions are generated through **user interaction** and/or **LLM-driven decision making**.

2. **Research Planning**  
   – Plans are categorized into two types:
   - **Static planning** – A complete plan is defined upfront and executed sequentially.
   - **Dynamic planning** – The plan is **continuously adjusted** during the research process.  
     ➤ *Current state-of-the-art methods predominantly adopt **dynamic planning**.*

3. **Information Retrieval**  
   – Information is gathered from multiple sources: **local databases**, **specialized APIs**, and **web search engines**.

4. **Answer Generation or Report Writing**  
   – The output is tailored to the task: concise answers for QA, or structured, detailed reports for report generation.

---

## 3. Optimization Techniques for DeepResearch

Three main approaches are used to enhance DeepResearch performance:

| Technique                        | Description                                                  |
| -------------------------------- | ------------------------------------------------------------ |
| **Workflow Prompt Engineering**  | Design specialized prompts and overall workflows to leverage LLMs as the base reasoning engine. |
| **Supervised Fine-Tuning (SFT)** | Fine-tune models on existing DeepResearch datasets to directly improve tool-calling, reasoning, information synthesis, and report-writing capabilities. |
| **Reinforcement Learning (RL)**  | Construct training data and apply RL methods (e.g., **DPO**, **GRPO**) to train models, boosting overall performance through reward-based learning. |

---

## 4. Major Bottlenecks

Despite progress, several critical challenges remain:

- **Incomplete Information Retrieval**  
  – Experiments show that many models **fail to retrieve all required information**, with coverage often **below 50%**.

- **Weak Compositional Reasoning**  
  – Even when provided with **full URLs** to relevant sources, models still underperform. Their ability to **reason over and synthesize large volumes of fragmented information** is limited.

- **Context Window Constraints**  
  – DeepResearch requires referencing vast amounts of information. Key issues include:
  - How to **judge relevance and correctness** of each piece of information.
  - How to **avoid exceeding the model's context window**.
  - How to **preserve and manage already-retrieved information** for later reference.

