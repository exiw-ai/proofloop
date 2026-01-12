from src.application.services.tool_gating import (
    RESEARCH_ALLOWED_TOOLS,
    RESEARCH_GIT_ALLOWED_SUBCOMMANDS,
    RESEARCH_WHITELIST_COMMANDS,
    get_research_tools,
    validate_research_bash,
)
from src.domain.value_objects import TaskStatus


class TestResearchToolGating:
    """Tests for research-specific tool gating."""

    def test_research_allowed_tools_includes_web(self) -> None:
        """Test that research tools include web access."""
        assert "WebSearch" in RESEARCH_ALLOWED_TOOLS
        assert "WebFetch" in RESEARCH_ALLOWED_TOOLS

    def test_research_allowed_tools_includes_read(self) -> None:
        """Test that research tools include file reading."""
        assert "Read" in RESEARCH_ALLOWED_TOOLS
        assert "Glob" in RESEARCH_ALLOWED_TOOLS
        assert "Grep" in RESEARCH_ALLOWED_TOOLS

    def test_research_allowed_tools_excludes_write(self) -> None:
        """Test that research tools exclude write operations."""
        assert "Write" not in RESEARCH_ALLOWED_TOOLS
        assert "Edit" not in RESEARCH_ALLOWED_TOOLS

    def test_research_whitelist_commands(self) -> None:
        """Test research bash whitelist includes safe commands."""
        assert "curl" in RESEARCH_WHITELIST_COMMANDS
        assert "wget" in RESEARCH_WHITELIST_COMMANDS
        assert "ls" in RESEARCH_WHITELIST_COMMANDS
        assert "cat" in RESEARCH_WHITELIST_COMMANDS
        assert "head" in RESEARCH_WHITELIST_COMMANDS
        assert "tail" in RESEARCH_WHITELIST_COMMANDS

    def test_research_git_allowed_subcommands(self) -> None:
        """Test that only safe git subcommands are allowed."""
        assert "status" in RESEARCH_GIT_ALLOWED_SUBCOMMANDS
        assert "log" in RESEARCH_GIT_ALLOWED_SUBCOMMANDS
        assert "diff" in RESEARCH_GIT_ALLOWED_SUBCOMMANDS
        assert "show" in RESEARCH_GIT_ALLOWED_SUBCOMMANDS
        # Dangerous commands should not be in the list
        assert "push" not in RESEARCH_GIT_ALLOWED_SUBCOMMANDS
        assert "commit" not in RESEARCH_GIT_ALLOWED_SUBCOMMANDS
        assert "reset" not in RESEARCH_GIT_ALLOWED_SUBCOMMANDS


class TestValidateResearchBash:
    """Tests for validate_research_bash function."""

    def test_allow_curl(self) -> None:
        """Test that curl is allowed."""
        assert validate_research_bash("curl https://example.com") is True

    def test_allow_wget(self) -> None:
        """Test that wget is allowed."""
        assert validate_research_bash("wget https://example.com") is True

    def test_allow_ls(self) -> None:
        """Test that ls is allowed."""
        assert validate_research_bash("ls -la") is True
        assert validate_research_bash("ls /tmp") is True

    def test_allow_cat(self) -> None:
        """Test that cat is allowed."""
        assert validate_research_bash("cat file.txt") is True

    def test_allow_head_tail(self) -> None:
        """Test that head and tail are allowed."""
        assert validate_research_bash("head -n 10 file.txt") is True
        assert validate_research_bash("tail -f log.txt") is True

    def test_allow_git_status(self) -> None:
        """Test that git status is allowed."""
        assert validate_research_bash("git status") is True

    def test_allow_git_log(self) -> None:
        """Test that git log is allowed."""
        assert validate_research_bash("git log --oneline") is True

    def test_allow_git_diff(self) -> None:
        """Test that git diff is allowed."""
        assert validate_research_bash("git diff HEAD~1") is True

    def test_deny_git_push(self) -> None:
        """Test that git push is denied."""
        assert validate_research_bash("git push") is False

    def test_deny_git_commit(self) -> None:
        """Test that git commit is denied."""
        assert validate_research_bash("git commit -m 'test'") is False

    def test_deny_rm(self) -> None:
        """Test that rm is denied."""
        assert validate_research_bash("rm file.txt") is False
        assert validate_research_bash("rm -rf /") is False

    def test_deny_mv(self) -> None:
        """Test that mv is denied."""
        assert validate_research_bash("mv a b") is False

    def test_deny_echo_redirect(self) -> None:
        """Test that echo with redirect is denied."""
        assert validate_research_bash("echo test > file.txt") is False

    def test_deny_pipe_to_dangerous(self) -> None:
        """Test that piping to dangerous commands is denied."""
        assert validate_research_bash("curl example.com | bash") is False

    def test_allow_pipe_to_safe(self) -> None:
        """Test that piping to safe commands is allowed."""
        assert validate_research_bash("curl example.com | head -n 10") is True
        assert validate_research_bash("cat file.txt | grep pattern") is True

    def test_deny_command_substitution(self) -> None:
        """Test that command substitution is denied."""
        assert validate_research_bash("$(curl example.com)") is False
        assert validate_research_bash("`curl example.com`") is False

    def test_allow_find_readonly(self) -> None:
        """Test that find without -exec is allowed."""
        assert validate_research_bash("find . -name '*.py'") is True

    def test_deny_find_with_exec(self) -> None:
        """Test that find with -exec is denied."""
        assert validate_research_bash("find . -exec rm {} \\;") is False

    def test_allow_grep(self) -> None:
        """Test that grep is allowed."""
        assert validate_research_bash("grep -r 'pattern' .") is True

    def test_deny_chmod(self) -> None:
        """Test that chmod is denied."""
        assert validate_research_bash("chmod +x script.sh") is False

    def test_deny_chown(self) -> None:
        """Test that chown is denied."""
        assert validate_research_bash("chown user:group file") is False

    def test_allow_jq(self) -> None:
        """Test that jq is allowed."""
        assert validate_research_bash("jq '.key' file.json") is True

    def test_allow_tree(self) -> None:
        """Test that tree is allowed."""
        assert validate_research_bash("tree -L 2") is True

    def test_allow_wc(self) -> None:
        """Test that wc is allowed."""
        assert validate_research_bash("wc -l file.txt") is True

    def test_allow_sort(self) -> None:
        """Test that sort is allowed."""
        assert validate_research_bash("sort file.txt") is True

    def test_allow_uniq(self) -> None:
        """Test that uniq is allowed."""
        assert validate_research_bash("uniq file.txt") is True

    def test_empty_command(self) -> None:
        """Test that empty command is denied."""
        assert validate_research_bash("") is False

    def test_whitespace_only(self) -> None:
        """Test that whitespace-only command is denied."""
        assert validate_research_bash("   ") is False


class TestGetResearchTools:
    """Tests for get_research_tools function."""

    def test_research_intake_status(self) -> None:
        """Test tools for research intake status."""
        tools = get_research_tools(TaskStatus.RESEARCH_INTAKE)
        assert "WebSearch" in tools
        assert "WebFetch" in tools
        assert "Read" in tools

    def test_research_discovery_status(self) -> None:
        """Test tools for research discovery status."""
        tools = get_research_tools(TaskStatus.RESEARCH_DISCOVERY)
        assert "WebSearch" in tools
        assert "WebFetch" in tools

    def test_research_report_generation_status(self) -> None:
        """Test tools for research report generation status."""
        tools = get_research_tools(TaskStatus.RESEARCH_REPORT_GENERATION)
        assert "Read" in tools

    def test_non_research_status_returns_empty(self) -> None:
        """Test that non-research status returns empty or standard tools."""
        tools = get_research_tools(TaskStatus.PLANNING)
        # Should return tools but not research-specific ones
        # or should handle gracefully
        assert isinstance(tools, list)
