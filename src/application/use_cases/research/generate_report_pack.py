from src.domain.entities import Task
from src.domain.ports.agent_port import AgentPort, MessageCallback
from src.domain.value_objects import TEMPLATE_SPECS, ReportPackTemplate, TaskStatus
from src.infrastructure.research import KnowledgeBaseStore, ReportPackStore


class GenerateReportPack:
    """Use case for generating report pack."""

    def __init__(
        self,
        agent: AgentPort,
        kb_store: KnowledgeBaseStore,
        report_store: ReportPackStore,
    ):
        self.agent = agent
        self.kb_store = kb_store
        self.report_store = report_store

    async def run(
        self,
        task: Task,
        template: ReportPackTemplate,
        on_message: MessageCallback | None = None,
    ) -> bool:
        """Generate report files from knowledge base."""
        task.transition_to(TaskStatus.RESEARCH_REPORT_GENERATION)

        # Create report pack
        pack = await self.report_store.create_report_pack(task.id, template)

        # Load knowledge base data
        sources = await self.kb_store.list_sources()
        findings = await self.kb_store.list_findings()

        # Build context for report generation
        source_summaries = [f"- [{s.source_key}] {s.title}: {s.url}" for s in sources[:50]]
        finding_summaries = [f"- {f.content[:200]}... (topics: {f.topics})" for f in findings[:100]]

        spec = TEMPLATE_SPECS[template]

        for filename in spec.required_files:
            section_name = filename.replace(".md", "").replace("_", " ").title()

            prompt = f"""Generate the "{section_name}" section for the research report.

Research Task: {task.description}
Goals: {task.goals}

Available Sources ({len(sources)} total):
{chr(10).join(source_summaries[:20])}

Key Findings ({len(findings)} total):
{chr(10).join(finding_summaries[:30])}

Template: {template.value}
Section: {filename}

Requirements:
1. Use [@source_key] format for citations (e.g., [@smith2024])
2. Only cite sources from the list above
3. Be comprehensive but concise
4. Include specific findings and evidence

Generate the markdown content for this section. Do not include the section header - start directly with the content."""

            from src.application.services.tool_gating import get_research_tools

            result = await self.agent.execute(
                prompt=prompt,
                allowed_tools=get_research_tools(task.status),
                cwd=".",
                on_message=on_message,
            )

            # Clean up the content
            content = result.final_response.strip()

            # Add section header
            full_content = f"# {section_name}\n\n{content}"

            await self.report_store.save_report_file(filename, full_content)

        # Update pack status
        pack = await self.report_store.update_pack_status(pack)

        # Calculate metrics
        metrics = {
            "sources_count": float(len(sources)),
            "findings_count": float(len(findings)),
            "coverage": 1.0
            if not pack.missing_files
            else len(pack.present_files) / len(pack.required_files),
        }

        # Save manifest
        await self.report_store.save_manifest(pack, metrics)

        return pack.status == "complete"
