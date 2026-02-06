"""
Claude Code Session Parser
セッション履歴（JSONL）をパースしてObsidian（TetsuyaSynapse）に保存

機能:
- 追記モード: 新しい行だけを処理（既存記録との競合を防止）
- 日付ベースのフィルタリング: 日付ごとにファイルを分割
"""

import json
import sys
import io
from pathlib import Path
from datetime import datetime, date
from dataclasses import dataclass, field
from typing import Optional
from collections import defaultdict
import re

# Windows環境での文字化け対策
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')


@dataclass
class Message:
    """会話メッセージ"""
    uuid: str
    role: str  # user / assistant
    content: str
    timestamp: datetime
    parent_uuid: Optional[str] = None
    tool_uses: list = field(default_factory=list)


@dataclass
class Session:
    """セッション情報"""
    session_id: str
    project_path: str
    version: str
    start_time: datetime
    end_time: datetime
    messages: list[Message] = field(default_factory=list)


class ClaudeSessionParser:
    """Claude Codeセッション履歴パーサー"""

    CLAUDE_PROJECTS_DIR = Path.home() / ".claude" / "projects"
    STATE_FILE = ".claude_parser_state.json"

    def __init__(self, vault_path: str = r"G:\マイドライブ\obsidian\TetsuyaSynapse"):
        self.vault_path = Path(vault_path)
        self.sessions_dir = self.vault_path / "90-Claude" / "sessions"
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
        self.state_file = self.sessions_dir / self.STATE_FILE
        self.state = self._load_state()

    def _load_state(self) -> dict:
        """処理状態を読み込む"""
        if self.state_file.exists():
            try:
                return json.loads(self.state_file.read_text(encoding='utf-8'))
            except (json.JSONDecodeError, IOError):
                pass
        return {"processed_lines": {}}

    def _save_state(self):
        """処理状態を保存"""
        self.state_file.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2),
            encoding='utf-8'
        )

    def parse_jsonl_incremental(self, jsonl_path: Path) -> dict[date, list[Message]]:
        """JSONLファイルを増分パースして日付ごとにメッセージを返す"""
        file_key = str(jsonl_path)
        last_line = self.state["processed_lines"].get(file_key, 0)

        messages_by_date: dict[date, list[Message]] = defaultdict(list)
        session_info = {"project_path": "", "version": ""}
        current_line = 0

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                current_line += 1

                # 既に処理済みの行はスキップ
                if current_line <= last_line:
                    continue

                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                # セッション情報を抽出
                if not session_info["project_path"] and 'cwd' in data:
                    session_info["project_path"] = data['cwd']
                if not session_info["version"] and 'version' in data:
                    session_info["version"] = data['version']

                # メッセージを抽出
                if data.get('type') in ('user', 'assistant') and 'message' in data:
                    msg_data = data['message']
                    msg_content = msg_data.get('content', [])

                    # tool_resultメッセージはスキップ
                    if self._is_tool_result(msg_content):
                        continue

                    content = self._extract_content(msg_content)
                    tool_uses = self._extract_tool_uses(msg_content)

                    # 空メッセージ、内部メッセージはスキップ
                    if not content and not tool_uses:
                        continue

                    timestamp = datetime.fromisoformat(
                        data['timestamp'].replace('Z', '+00:00')
                    )

                    msg = Message(
                        uuid=data.get('uuid', ''),
                        role=msg_data.get('role', data['type']),
                        content=content,
                        timestamp=timestamp,
                        parent_uuid=data.get('parentUuid'),
                        tool_uses=tool_uses
                    )

                    # 日付ごとに分類
                    msg_date = timestamp.date()
                    messages_by_date[msg_date].append(msg)

        # 処理済み行を更新
        self.state["processed_lines"][file_key] = current_line
        self._save_state()

        return messages_by_date, session_info

    def _extract_content(self, content) -> str:
        """contentからテキストを抽出"""
        # 文字列の場合はそのまま返す（ユーザーメッセージ）
        if isinstance(content, str):
            return self._clean_content(content)

        # 配列の場合は各要素を処理（アシスタントメッセージ）
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get('type') == 'text':
                    texts.append(item.get('text', ''))
                # thinkingは除外（内部的な思考プロセス）
            elif isinstance(item, str):
                texts.append(item)

        return self._clean_content('\n'.join(texts))

    def _clean_content(self, text: str) -> str:
        """コンテンツからノイズを除去"""
        if not text:
            return ""

        # system-reminderタグを除去
        text = re.sub(r'<system-reminder>.*?</system-reminder>', '', text, flags=re.DOTALL)
        # local-commandタグを除去
        text = re.sub(r'<local-command-[^>]*>.*?</local-command-[^>]*>', '', text, flags=re.DOTALL)
        # ide_opened_fileなどの内部メッセージを除去
        text = re.sub(r'^ide_opened_file.*$', '', text, flags=re.MULTILINE)
        # claudeMdタグを除去
        text = re.sub(r'# claudeMd.*?IMPORTANT:', '', text, flags=re.DOTALL)

        return text.strip()

    def _extract_tool_uses(self, content) -> list:
        """contentからツール使用を抽出"""
        # 文字列の場合はツール使用なし
        if isinstance(content, str):
            return []

        tools = []
        for item in content:
            if isinstance(item, dict) and item.get('type') == 'tool_use':
                tools.append({
                    'name': item.get('name', ''),
                    'input': item.get('input', {})
                })
        return tools

    def _is_tool_result(self, content) -> bool:
        """tool_resultメッセージかどうかを判定"""
        if isinstance(content, str):
            return False

        for item in content:
            if isinstance(item, dict) and item.get('type') == 'tool_result':
                return True
        return False

    def append_to_daily_file(self, msg_date: date, messages: list[Message], session_info: dict):
        """日付ファイルにメッセージを追記"""
        date_str = msg_date.strftime('%Y-%m-%d')
        filename = f"{date_str}_auto.md"
        filepath = self.sessions_dir / filename

        # 新規ファイルの場合はヘッダーを作成
        if not filepath.exists():
            header = self._generate_header(msg_date, session_info)
            filepath.write_text(header, encoding='utf-8')

        # メッセージを追記
        with open(filepath, 'a', encoding='utf-8') as f:
            for msg in messages:
                f.write(self._format_message(msg))

    def _generate_header(self, msg_date: date, session_info: dict) -> str:
        """日付ファイルのヘッダーを生成"""
        return f"""---
date: {msg_date.strftime('%Y-%m-%d')}
project: {session_info.get('project_path', '')}
claude_version: {session_info.get('version', '')}
tags: [claude-session, auto-generated]
---

# Claude Code セッション - {msg_date.strftime('%Y年%m月%d日')}

"""

    def _format_message(self, msg: Message) -> str:
        """メッセージをMarkdown形式にフォーマット"""
        lines = []
        role_label = "👤 User" if msg.role == 'user' else "🤖 Claude"
        time_str = msg.timestamp.strftime('%H:%M:%S')

        lines.append(f"### {role_label} ({time_str})")
        lines.append("")

        if msg.content:
            lines.append(msg.content)
            lines.append("")

        if msg.tool_uses:
            lines.append("**ツール使用:**")
            for tool in msg.tool_uses:
                lines.append(f"- `{tool['name']}`")
            lines.append("")

        return '\n'.join(lines) + '\n'

    def list_sessions(self, project_filter: str = None) -> list[Path]:
        """利用可能なセッションファイルを一覧"""
        sessions = []
        for project_dir in self.CLAUDE_PROJECTS_DIR.iterdir():
            if not project_dir.is_dir():
                continue

            # プロジェクトフィルター
            if project_filter and project_filter not in project_dir.name:
                continue

            # メインセッションのみ（agent-で始まらないもの）
            for jsonl_file in project_dir.glob("*.jsonl"):
                if not jsonl_file.name.startswith("agent-"):
                    sessions.append(jsonl_file)

        return sorted(sessions, key=lambda p: p.stat().st_mtime, reverse=True)

    def sync_all(self, project_filter: str = None):
        """すべてのセッションを同期（増分処理）"""
        sessions = self.list_sessions(project_filter)
        total_new = 0

        for jsonl_path in sessions:
            messages_by_date, session_info = self.parse_jsonl_incremental(jsonl_path)

            for msg_date, messages in messages_by_date.items():
                if messages:
                    self.append_to_daily_file(msg_date, messages, session_info)
                    total_new += len(messages)

        return total_new

    # === レガシー互換（一括処理）===

    def parse_jsonl(self, jsonl_path: Path) -> Session:
        """JSONLファイルをパースしてSessionオブジェクトを返す（レガシー）"""
        messages = []
        session_id = None
        project_path = ""
        version = ""
        timestamps = []

        with open(jsonl_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if not session_id and 'sessionId' in data:
                    session_id = data['sessionId']
                if not project_path and 'cwd' in data:
                    project_path = data['cwd']
                if not version and 'version' in data:
                    version = data['version']

                if data.get('type') in ('user', 'assistant') and 'message' in data:
                    msg_data = data['message']
                    msg_content = msg_data.get('content', [])

                    if self._is_tool_result(msg_content):
                        continue

                    content = self._extract_content(msg_content)
                    tool_uses = self._extract_tool_uses(msg_content)

                    if content or tool_uses:
                        timestamp = datetime.fromisoformat(
                            data['timestamp'].replace('Z', '+00:00')
                        )
                        timestamps.append(timestamp)
                        messages.append(Message(
                            uuid=data.get('uuid', ''),
                            role=msg_data.get('role', data['type']),
                            content=content,
                            timestamp=timestamp,
                            parent_uuid=data.get('parentUuid'),
                            tool_uses=tool_uses
                        ))

        return Session(
            session_id=session_id or jsonl_path.stem,
            project_path=project_path,
            version=version,
            start_time=min(timestamps) if timestamps else datetime.now(),
            end_time=max(timestamps) if timestamps else datetime.now(),
            messages=messages
        )

    def generate_summary(self, session: Session) -> dict:
        """セッションの要約を生成"""
        user_messages = [m for m in session.messages if m.role == 'user' and m.content]
        first_topic = user_messages[0].content[:200] if user_messages else "（不明）"

        tool_counts = {}
        for msg in session.messages:
            for tool in msg.tool_uses:
                name = tool['name']
                tool_counts[name] = tool_counts.get(name, 0) + 1

        top_tools = sorted(tool_counts.items(), key=lambda x: -x[1])[:5]

        return {
            'first_topic': first_topic,
            'message_count': len(session.messages),
            'user_message_count': len(user_messages),
            'duration_minutes': (session.end_time - session.start_time).total_seconds() / 60,
            'top_tools': top_tools
        }

    def save_to_obsidian(self, session: Session, summary: dict) -> Path:
        """ObsidianのMarkdown形式で保存（レガシー）"""
        date_str = session.start_time.strftime('%Y-%m-%d')
        time_str = session.start_time.strftime('%H%M')
        topic_slug = self._slugify(summary['first_topic'][:50])
        filename = f"{date_str}_{time_str}_{topic_slug}.md"

        md_content = self._generate_markdown(session, summary)
        output_path = self.sessions_dir / filename
        output_path.write_text(md_content, encoding='utf-8')
        return output_path

    def _slugify(self, text: str) -> str:
        """テキストをファイル名に使えるslugに変換"""
        text = re.sub(r'[<>:"/\\|?*\n\r]', '', text)
        text = text.strip()[:50]
        return text or "session"

    def _generate_markdown(self, session: Session, summary: dict) -> str:
        """Markdownコンテンツを生成"""
        lines = [
            "---",
            f"session_id: {session.session_id}",
            f"project: {session.project_path}",
            f"claude_version: {session.version}",
            f"date: {session.start_time.strftime('%Y-%m-%d')}",
            f"start_time: {session.start_time.strftime('%H:%M:%S')}",
            f"end_time: {session.end_time.strftime('%H:%M:%S')}",
            f"duration_minutes: {summary['duration_minutes']:.1f}",
            f"message_count: {summary['message_count']}",
            "tags: [claude-session]",
            "---",
            "",
            "# セッション要約",
            "",
            f"**開始トピック**: {summary['first_topic'][:200]}",
            "",
            "## 統計",
            f"- メッセージ数: {summary['message_count']}",
            f"- ユーザー入力: {summary['user_message_count']}",
            f"- 所要時間: {summary['duration_minutes']:.1f}分",
            "",
            "## 使用ツール（Top 5）",
        ]

        for tool_name, count in summary['top_tools']:
            lines.append(f"- {tool_name}: {count}回")

        lines.extend(["", "---", "", "# 会話ログ", ""])

        for msg in session.messages:
            role_label = "👤 User" if msg.role == 'user' else "🤖 Claude"
            time_str = msg.timestamp.strftime('%H:%M:%S')

            lines.append(f"### {role_label} ({time_str})")
            lines.append("")

            if msg.content:
                lines.append(msg.content)
                lines.append("")

            if msg.tool_uses:
                lines.append("**ツール使用:**")
                for tool in msg.tool_uses:
                    lines.append(f"- `{tool['name']}`")
                lines.append("")

        return '\n'.join(lines)

    def process_recent(self, limit: int = 5, project_filter: str = None):
        """最新のセッションを処理（レガシー）"""
        sessions = self.list_sessions(project_filter)[:limit]
        results = []

        for jsonl_path in sessions:
            print(f"Processing: {jsonl_path.name}")
            session = self.parse_jsonl(jsonl_path)
            summary = self.generate_summary(session)
            output_path = self.save_to_obsidian(session, summary)
            results.append({
                'source': jsonl_path,
                'output': output_path,
                'summary': summary
            })
            print(f"  -> Saved: {output_path.name}")

        return results


def main():
    """メイン実行"""
    import argparse

    arg_parser = argparse.ArgumentParser(
        description="Claude Codeセッション履歴をObsidianに保存"
    )
    arg_parser.add_argument(
        "-l", "--limit", type=int, default=5,
        help="処理するセッション数（デフォルト: 5）"
    )
    arg_parser.add_argument(
        "-p", "--project", type=str, default=None,
        help="プロジェクト名でフィルター"
    )
    arg_parser.add_argument(
        "--list", action="store_true",
        help="セッション一覧を表示（処理はしない）"
    )
    arg_parser.add_argument(
        "-s", "--session", type=str, default=None,
        help="特定のセッションID（UUID）を処理"
    )
    arg_parser.add_argument(
        "-v", "--vault", type=str,
        default=r"G:\マイドライブ\obsidian\TetsuyaSynapse",
        help="Obsidian Vaultのパス"
    )
    arg_parser.add_argument(
        "--sync", action="store_true",
        help="増分同期モード（追記）"
    )
    arg_parser.add_argument(
        "--reset", action="store_true",
        help="処理状態をリセット（全件再処理）"
    )

    args = arg_parser.parse_args()

    session_parser = ClaudeSessionParser(vault_path=args.vault)

    print("=== Claude Session Parser ===\n")

    # 状態リセット
    if args.reset:
        session_parser.state = {"processed_lines": {}}
        session_parser._save_state()
        print("処理状態をリセットしました\n")

    # 一覧表示モード
    if args.list:
        sessions = session_parser.list_sessions(args.project)
        print(f"利用可能なセッション: {len(sessions)}件\n")
        for i, s in enumerate(sessions[:20], 1):
            mtime = datetime.fromtimestamp(s.stat().st_mtime)
            print(f"  {i:2}. [{mtime.strftime('%Y-%m-%d %H:%M')}] {s.parent.name}")
            print(f"      {s.name}")
        if len(sessions) > 20:
            print(f"\n  ... 他 {len(sessions) - 20}件")
        return

    # 増分同期モード
    if args.sync:
        new_count = session_parser.sync_all(args.project)
        print(f"同期完了: {new_count}件の新しいメッセージを追記")
        return

    # 特定セッション処理モード
    if args.session:
        sessions = session_parser.list_sessions(args.project)
        target = None
        for s in sessions:
            if args.session in s.name:
                target = s
                break

        if not target:
            print(f"セッション '{args.session}' が見つかりません")
            return

        print(f"Processing: {target.name}")
        session = session_parser.parse_jsonl(target)
        summary = session_parser.generate_summary(session)
        output_path = session_parser.save_to_obsidian(session, summary)
        print(f"  -> Saved: {output_path.name}")
        return

    # 通常モード：最新N件を処理（レガシー）
    sessions = session_parser.list_sessions(args.project)
    print(f"利用可能なセッション: {len(sessions)}件\n")

    if sessions:
        print(f"最新{args.limit}件を処理します...\n")
        results = session_parser.process_recent(limit=args.limit, project_filter=args.project)

        print(f"\n処理完了: {len(results)}件")
        for r in results:
            print(f"  - {r['output'].name}")


if __name__ == "__main__":
    main()
