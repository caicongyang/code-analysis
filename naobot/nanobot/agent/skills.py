"""
================================================================================
NanoBot Skills Loader - 技能加载器模块
================================================================================

功能描述:
    负责加载和管理 Agent 的技能（Skills）。技能是 Markdown 文件，
    包含如何使用特定工具或执行特定任务的说明。

技能类型:
    1. 工作空间技能 (Workspace Skills):
       - 位置: workspace/skills/{skill-name}/SKILL.md
       - 优先级: 高（优先加载）
       - 用途: 用户自定义的技能

    2. 内置技能 (Built-in Skills):
       - 位置: nanobot/skills/{skill-name}/SKILL.md
       - 优先级: 低（被工作空间技能覆盖）
       - 用途: 系统自带的技能

技能文件结构:
    skills/
    ├── python/
    │   └── SKILL.md          # Python 技能
    ├── git/
    │   └── SKILL.md          # Git 技能
    └── docker/
        └── SKILL.md          # Docker 技能

SKILL.md 文件格式:
    ---
    name: skill-name
    description: 技能描述
    metadata:
      nanobot:
        always: true/false  # 是否始终加载
        requires:
          bins: [命令列表]
          env: [环境变量列表]
    ---
    
    # 技能内容
    ## 使用场景
    ## 使用方法
    ## 示例

渐进式加载:
    1. Always Skills: 始终包含在系统提示词中
    2. Available Skills: 只显示摘要，按需读取

================================================================================
"""

import json
import os
import re
import shutil
from pathlib import Path

# 内置技能目录常量
# 相对于当前文件的位置
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent / "skills"


class SkillsLoader:
    """
    ========================================================================
    SkillsLoader - 技能加载器类
    ========================================================================
    
    负责管理 Agent 的所有技能。
    
    核心功能:
        1. list_skills(): 列出所有可用技能
        2. load_skill(): 加载指定技能的内容
        3. load_skills_for_context(): 加载多个技能到上下文
        4. build_skills_summary(): 构建技能摘要
        5. get_always_skills(): 获取始终加载的技能
    
    技能搜索顺序:
        1. 工作空间 skills/ 目录
        2. 内置 nanobot/skills/ 目录
    
    ========================================================================
    """
    
    def __init__(self, workspace: Path, builtin_skills_dir: Path | None = None):
        """
        初始化技能加载器
        
        参数:
            workspace: Path，工作空间根目录
            builtin_skills_dir: Path | None，内置技能目录
        
        初始化过程:
            1. 保存工作空间路径
            2. 确定工作空间技能目录
            3. 确定内置技能目录
        """
        self.workspace = workspace
        self.workspace_skills = workspace / "skills"
        self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
    
    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """
        列出所有可用技能
        
        技能信息包含:
            - name: 技能名称
            - path: SKILL.md 文件路径
            - source: 来源 (workspace 或 builtin)
        
        参数:
            filter_unavailable: bool，是否过滤掉有未满足需求的技能
                - True: 只返回满足所有需求的技能
                - False: 返回所有技能
        
        返回:
            list[dict[str, str]]，技能信息列表
        
        使用示例:
            # 列出所有满足需求的技能
            skills = loader.list_skills()
            for s in skills:
                print(f"{s['name']} ({s['source']})")
            
            # 列出所有技能（包括未满足需求的）
            all_skills = loader.list_skills(filter_unavailable=False)
        """
        skills = []
        
        # ====================================================================
        # 1. 工作空间技能（高优先级）
        # ====================================================================
        if self.workspace_skills.exists():
            for skill_dir in self.workspace_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        skills.append({
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": "workspace"
                        })
        
        # ====================================================================
        # 2. 内置技能（低优先级）
        # ====================================================================
        if self.builtin_skills and self.builtin_skills.exists():
            for skill_dir in self.builtin_skills.iterdir():
                if skill_dir.is_dir():
                    skill_file = skill_dir / "SKILL.md"
                    # 避免重复添加（工作空间有同名技能时）
                    if (skill_file.exists() and 
                        not any(s["name"] == skill_dir.name for s in skills)):
                        skills.append({
                            "name": skill_dir.name,
                            "path": str(skill_file),
                            "source": "builtin"
                        })
        
        # ====================================================================
        # 3. 按需求过滤
        # ====================================================================
        if filter_unavailable:
            return [s for s in skills 
                    if self._check_requirements(
                        self._get_skill_meta(s["name"])
                    )]
        return skills
    
    def load_skill(self, name: str) -> str | None:
        """
        加载指定技能的内容
        
        搜索顺序:
            1. workspace/skills/{name}/SKILL.md
            2. nanobot/skills/{name}/SKILL.md
        
        参数:
            name: str，技能名称
        
        返回:
            str | None，SKILL.md 的完整内容
            如果技能不存在，返回 None
        
        使用示例:
            # 加载 Python 技能
            python_skill = loader.load_skill("python")
            if python_skill:
                print(python_skill[:100])
        """
        # 首先检查工作空间
        workspace_skill = self.workspace_skills / name / "SKILL.md"
        if workspace_skill.exists():
            return workspace_skill.read_text(encoding="utf-8")
        
        # 检查内置技能
        if self.builtin_skills:
            builtin_skill = self.builtin_skills / name / "SKILL.md"
            if builtin_skill.exists():
                return builtin_skill.read_text(encoding="utf-8")
        
        return None
    
    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """
        加载多个技能用于 Agent 上下文
        
        用途:
            - 将指定技能的内容添加到系统提示词
            - 用于"始终加载"的技能
        
        参数:
            skill_names: list[str]，要加载的技能名称列表
        
        处理逻辑:
            1. 遍历每个技能名称
            2. 加载技能内容
            3. 去除 frontmatter
            4. 用分隔符连接
        
        返回:
            str，格式化的技能内容
            如果没有技能，返回空字符串
        
        使用示例:
            # 加载多个技能
            content = loader.load_skills_for_context(
                ["python", "git", "docker"]
            )
        """
        parts = []
        
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                # 去除 frontmatter
                content = self._strip_frontmatter(content)
                parts.append(f"### Skill: {name}\n\n{content}")
        
        return "\n\n---\n\n".join(parts) if parts else ""
    
    def build_skills_summary(self) -> str:
        """
        构建所有技能的摘要（用于渐进式加载）
        
        用途:
            - 在系统提示词中列出所有可用技能
            - Agent 可以看到技能列表，按需读取
        
        输出格式:
            <skills>
              <skill available="true/false">
                <name>技能名称</name>
                <description>技能描述</description>
                <location>技能路径</location>
                <requires>缺失的需求</requires>
              </skill>
            </skills>
        
        不可用技能会显示:
            - available="false"
            - 缺失的 CLI 命令或环境变量
        
        返回:
            str，XML 格式的技能摘要
            如果没有技能，返回空字符串
        
        使用示例:
            summary = loader.build_skills_summary()
            if summary:
                print(summary)
        """
        all_skills = self.list_skills(filter_unavailable=False)
        if not all_skills:
            return ""
        
        def escape_xml(s: str) -> str:
            """转义 XML 特殊字符"""
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        lines = ["<skills>"]
        
        for s in all_skills:
            name = escape_xml(s["name"])
            path = s["path"]
            desc = escape_xml(self._get_skill_description(s["name"]))
            skill_meta = self._get_skill_meta(s["name"])
            available = self._check_requirements(skill_meta)
            
            lines.append(f'  <skill available="{str(available).lower()}">')
            lines.append(f"    <name>{name}</name>")
            lines.append(f"    <description>{desc}</description>")
            lines.append(f"    <location>{path}</location>")
            
            # 显示不可用技能的需求
            if not available:
                missing = self._get_missing_requirements(skill_meta)
                if missing:
                    lines.append(f"    <requires>{escape_xml(missing)}</requires>")
            
            lines.append(f"  </skill>")
        
        lines.append("</skills>")
        
        return "\n".join(lines)
    
    def _get_missing_requirements(self, skill_meta: dict) -> str:
        """
        获取缺失的需求描述
        
        检查内容:
            - bins: CLI 命令是否存在于 PATH 中
            - env: 环境变量是否已设置
        
        参数:
            skill_meta: dict，技能的元数据
        
        返回:
            str，格式化的缺失需求描述
        """
        missing = []
        requires = skill_meta.get("requires", {})
        
        # 检查 CLI 命令
        for b in requires.get("bins", []):
            if not shutil.which(b):
                missing.append(f"CLI: {b}")
        
        # 检查环境变量
        for env in requires.get("env", []):
            if not os.environ.get(env):
                missing.append(f"ENV: {env}")
        
        return ", ".join(missing)
    
    def _get_skill_description(self, name: str) -> str:
        """
        获取技能的描述
        
        优先从 frontmatter 的 description 字段获取
        
        参数:
            name: str，技能名称
        
        返回:
            str，技能描述
        """
        meta = self.get_skill_metadata(name)
        if meta and meta.get("description"):
            return meta["description"]
        return name
    
    def _strip_frontmatter(self, content: str) -> str:
        """
        从 Markdown 内容中去除 YAML frontmatter
        
        frontmatter 格式:
            ---
            name: skill-name
            description: xxx
            ---
            
            # 技能内容
        
        参数:
            content: str，完整的 Markdown 内容
        
        返回:
            str，去除 frontmatter 后的内容
        """
        if content.startswith("---"):
            match = re.match(r"^---\n.*?\n---\n", content, re.DOTALL)
            if match:
                return content[match.end():].strip()
        return content
    
    def _parse_nanobot_metadata(self, raw: str) -> dict:
        """
        解析 frontmatter 中的 nanobot 元数据
        
        元数据格式:
            metadata:
              nanobot:
                always: true
                requires:
                  bins: [cmd1, cmd2]
        
        参数:
            raw: str，metadata 字段的原始内容
        
        返回:
            dict，解析后的 nanobot 元数据
        """
        try:
            data = json.loads(raw)
            return data.get("nanobot", {}) if isinstance(data, dict) else {}
        except (json.JSONDecodeError, TypeError):
            return {}
    
    def _check_requirements(self, skill_meta: dict) -> bool:
        """
        检查技能的需求是否满足
        
        检查内容:
            - bins: CLI 命令是否可用
            - env: 环境变量是否已设置
        
        参数:
            skill_meta: dict，技能的元数据
        
        返回:
            bool，所有需求是否都满足
        """
        requires = skill_meta.get("requires", {})
        
        # 检查 CLI 命令
        for b in requires.get("bins", []):
            if not shutil.which(b):
                return False
        
        # 检查环境变量
        for env in requires.get("env", []):
            if not os.environ.get(env):
                return False
        
        return True
    
    def _get_skill_meta(self, name: str) -> dict:
        """
        获取技能的 nanobot 元数据
        
        从 frontmatter 解析:
            metadata:
              nanobot: {...}
        
        参数:
            name: str，技能名称
        
        返回:
            dict，技能的 nanobot 元数据
        """
        meta = self.get_skill_metadata(name) or {}
        return self._parse_nanobot_metadata(meta.get("metadata", ""))
    
    def get_always_skills(self) -> list[str]:
        """
        获取标记为"始终加载"的技能
        
        标记方式:
            metadata:
              nanobot:
                always: true
        
        返回:
            list[str]，满足需求的"始终加载"技能名称列表
        """
        result = []
        
        for s in self.list_skills(filter_unavailable=True):
            meta = self.get_skill_metadata(s["name"]) or {}
            skill_meta = self._parse_nanobot_metadata(meta.get("metadata", ""))
            
            # 检查 always 标记
            if (skill_meta.get("always") or meta.get("always")):
                result.append(s["name"])
        
        return result
    
    def get_skill_metadata(self, name: str) -> dict | None:
        """
        获取技能的完整元数据
        
        从 frontmatter 解析:
            ---
            name: skill-name
            description: xxx
            metadata: {...}
            ---
        
        参数:
            name: str，技能名称
        
        返回:
            dict | None，解析后的元数据
        """
        content = self.load_skill(name)
        if not content:
            return None
        
        # 解析 frontmatter
        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                metadata = {}
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        metadata[key.strip()] = value.strip().strip('"\'')
                return metadata
        
        return None