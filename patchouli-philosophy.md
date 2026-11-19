# Patchouli Philosophy

Patchouli is an LLM-wiki framework that helps users build an evolving personal knowledge base with the assistance of an LLM Agent. It distills scattered materials and insights gained through reading and reflection into interconnected, structured knowledge. Humans provide research goals, questions, judgment, and direction; the Agent handles reading materials, extracting content, discovering connections, synthesizing evidence, and organizing and maintaining the knowledge base. Both collaborate around the same knowledge base, allowing existing achievements to serve as the foundation for subsequent analysis and reasoning.

## Enabling Continuous Knowledge Accumulation

In Patchouli, the continuous evolution of the knowledge base is driven by two processes:

* **Material Compilation**: The Agent reads new materials, extracts valuable information, integrates it with existing knowledge in the knowledge base, and updates relevant topics, concepts, evidence, and relationships.
* **Interactive Distillation**: Users ask questions, conduct analyses, or instruct the Agent to establish higher-level connections and perform autonomous exploration around the knowledge in the Wiki. New interpretations, new connections, and other insights of lasting value formed during this process can be further distilled back into the knowledge base.

## Selecting Knowledge of Lasting Value

Content distilled into the knowledge base must possess clear research value—providing facts, explanations, methods, independent evidence, or questions worth tracking. When absorbing new content, the Agent should find the optimal placement based on existing knowledge: supplementing or updating existing pages, restructuring the knowledge architecture, or creating standalone new pages.

Patchouli's Wiki organizes content through different types of knowledge pages, such as:

* **Source Pages**: Distillations and understandings of a single material.
* **Concept Pages**: Aggregations of core concepts, methods, or questions that recur across multiple materials.
* **Synthesis Pages**: Horizontal comparisons across multiple sources, mapping out consensus, divergence, complementarity, and conditional differences.
* **Answer Pages**: Repositories of Q&As and insights with long-term reference value.

Links between pages weave individual nodes into a network, enabling subsequent reading and analysis to unfold naturally along existing threads of knowledge.

## From Sources to Knowledge

Patchouli compiles materials into progressive layers of knowledge:

1. **Raw Materials**: Original content entering the system—such as papers, web pages, and notes—in formats like PDF, HTML, etc.
2. **Reading Text**: Readable representations parsed from raw materials for the Agent to read, verify, and cite.
3. **Source Knowledge**: Structured understanding formed by the Agent around a single material, recording its key facts, methods, evidence, conditions, and explanations.
4. **Integrated Knowledge**: Concepts, cross-source comparisons and synthesis analyses, and Q&As with long-term reference value organized further on the basis of source knowledge.

Each layer carries different degrees of processing, abstraction, and integration. New materials enter in their raw state, are compiled into source knowledge via reading text, and then participate in higher-level knowledge integration; meanwhile, high-level knowledge maintains traceability through citation relationships, allowing layer-by-layer backtracking to the specific sources and texts that support it.

## On-Demand Reading and Traceability

The Agent selects relevant knowledge pages and layers to read based on the current question. Concept pages, synthesis pages, and answer pages provide existing holistic understandings and connections; source pages retain more complete distillations of specific materials to facilitate further verification of methods, evidence, and conditions.

When existing knowledge is insufficient to support the current analysis, the Agent can trace back along citation relationships to the reading text or raw materials to obtain the necessary details. New understandings of lasting value generated during this traceback are distilled back into the Wiki in reverse, allowing the knowledge base to be continuously supplemented and refined through actual use.

## Evidence and Reasoning

Patchouli emphasizes the verifiability of knowledge and rigor of argumentation. It distinguishes among **findings and claims directly stated by sources**, **extended interpretations made by the Agent based on sources**, and **synthetic judgments formed across sources**, clarifying the basis and reasoning chain for each. Important conclusions must retain their full preconditions, methodological pathways, and scope of applicability.

When synthesizing multiple sources, the Agent deeply compares research questions, theoretical assumptions, methodological designs, and concrete evidence, analyzing the intrinsic connections between different conclusions and the causes of their discrepancies. For any judgment derived therefrom, **its level of certainty must match the strength of the evidence and the rigor of the reasoning**; interpretations and hypotheses yet to be tested must be explicitly annotated with their derivation basis and key uncertainties.

## Knowledge Updates and Maintenance

As sources are revised, new evidence is added, and understanding deepens, the knowledge base must also evolve continuously. Accordingly, the Agent supplements, revises, or restructures relevant pages, clearly accounting for the material basis and reasoning judgments behind the changes.

**The Wiki's citation network** provides an index for systematic maintenance: when underlying source knowledge undergoes substantive changes, the Agent can trace to all concept pages, synthesis pages, and answer pages citing that source, re-evaluate the relevant claims, and update the affected content.

## Knowledge Operations and Tool Division of Labor

Through a set of task contracts tailored for knowledge work, Patchouli supports operations including material ingestion, information retrieval, knowledge Q&A, cross-source synthesis, proactive exploration, and knowledge organization and maintenance. Each contract defines task objectives, available resources, and expected deliverables, guiding the Agent to carry out corresponding work according to user intent.

The system assigns tasks requiring **semantic understanding and research judgment** to the Agent, while delegating **deterministic operations**—such as text extraction, citation parsing, index construction, consistency checks, and version management—to scripts. This division of labor allows the Agent to focus on the comprehension, organization, and reasoning of knowledge, while supporting the continuous operation and maintenance of the knowledge base with reliable tools.

## Continuous Improvement in Real-World Use

Patchouli relies on real-world knowledge work as the primary basis for continuous iteration. Actual interactions between the user and the Agent during material compilation, Q&A, synthesis, exploration, and maintenance provide direct feedback for identifying issues in knowledge organization, task prompts, and tool implementations, driving the continuous refinement of the framework.
