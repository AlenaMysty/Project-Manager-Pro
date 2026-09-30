"""
Система управления проектами v3.4
+ Комментарии к Эпикам и Задачам
+ История изменений комментариев
"""

from flask import Flask, render_template_string, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

DATABASE_URL = os.getenv('DATABASE_URL')
if DATABASE_URL:
    if DATABASE_URL.startswith("postgres://"):
        DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
else:
    basedir = os.path.abspath(os.path.dirname(__file__))
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(basedir, 'project_v3.db')

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)


# ==================== МОДЕЛИ ====================

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(150), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(20), default='#6366f1')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    epics = db.relationship('Epic', backref='project', lazy=True, cascade='all, delete-orphan')

    def to_dict(self):
        total_tasks = sum(len(e.tasks) for e in self.epics)
        done_tasks = sum(1 for e in self.epics for t in e.tasks if t.status == 'checked')
        return {
            'id': self.id, 'name': self.name,
            'description': self.description or '',
            'color': self.color,
            'epics_count': len(self.epics),
            'tasks_total': total_tasks, 'tasks_done': done_tasks,
            'progress': round(done_tasks / total_tasks * 100) if total_tasks else 0,
            'created_at': self.created_at.strftime('%d.%m.%Y')
        }


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    role = db.Column(db.String(100))
    email = db.Column(db.String(120))
    avatar_color = db.Column(db.String(20), default='#6366f1')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='employee', lazy=True)

    def to_dict(self, project_id=None):
        tasks = self.tasks
        if project_id:
            tasks = [t for t in tasks if t.epic.project_id == project_id]
        active = sum(1 for t in tasks if t.status in ('active', 'overdue'))
        overdue = sum(1 for t in tasks if t.status == 'overdue')
        done = sum(1 for t in tasks if t.status == 'checked')
        return {
            'id': self.id, 'name': self.name,
            'role': self.role or '—', 'email': self.email or '—',
            'avatar_color': self.avatar_color,
            'initials': ''.join([w[0].upper() for w in self.name.split()[:2]]),
            'tasks_total': len(tasks), 'tasks_active': active,
            'tasks_overdue': overdue, 'tasks_done': done,
            'workload': min(100, active * 20),
            'created_at': self.created_at.strftime('%d.%m.%Y')
        }


class Epic(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    color = db.Column(db.String(20), default='#8b5cf6')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tasks = db.relationship('Task', backref='epic', lazy=True, cascade='all, delete-orphan')
    comments = db.relationship('Comment', backref='epic', lazy=True,
                               cascade='all, delete-orphan',
                               foreign_keys='Comment.epic_id')

    def to_dict(self):
        total = len(self.tasks)
        done = sum(1 for t in self.tasks if t.status == 'checked')
        overdue = sum(1 for t in self.tasks if t.status == 'overdue')
        return {
            'id': self.id, 'project_id': self.project_id,
            'project_name': self.project.name,
            'project_color': self.project.color,
            'name': self.name, 'description': self.description or '',
            'color': self.color,
            'tasks_total': total, 'tasks_done': done, 'tasks_overdue': overdue,
            'progress': round(done / total * 100) if total else 0,
            'created_at': self.created_at.strftime('%d.%m.%Y')
        }


class Task(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    epic_id = db.Column(db.Integer, db.ForeignKey('epic.id'), nullable=False)
    employee_id = db.Column(db.Integer, db.ForeignKey('employee.id'), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    deadline = db.Column(db.DateTime, nullable=False)
    priority = db.Column(db.String(20), default='medium')
    status = db.Column(db.String(20), default='active')
    reminder_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    comments = db.relationship('Comment', backref='task', lazy=True,
                               cascade='all, delete-orphan',
                               foreign_keys='Comment.task_id')

    def to_dict(self):
        now = datetime.utcnow()
        delta = self.deadline - now
        hours_left = delta.total_seconds() / 3600

        if self.status == 'checked':
            status_label, status_class = '✅ Выполнено', 'checked'
        elif self.deadline < now:
            status_label, status_class = '🔴 Просрочено', 'overdue'
        elif hours_left < 24:
            status_label, status_class = '🟡 Менее суток', 'warning'
        else:
            status_label, status_class = '🟢 В срок', 'active'

        priority_map = {
            'low': ('🔵 Низкий', 'low'),
            'medium': ('🟡 Средний', 'medium'),
            'high': ('🔴 Высокий', 'high')
        }
        pr_label, pr_class = priority_map.get(self.priority, priority_map['medium'])

        if hours_left > 0:
            days = int(hours_left // 24)
            hrs = int(hours_left % 24)
            if days > 0:
                time_left_str = f'{days} дн. {hrs} ч.'
            else:
                mins = int((hours_left - hrs) * 60)
                time_left_str = f'{hrs} ч. {mins} мин.'
        else:
            abs_hours = abs(hours_left)
            days = int(abs_hours // 24)
            hrs = int(abs_hours % 24)
            if days > 0:
                time_left_str = f'на {days} дн. {hrs} ч.'
            else:
                time_left_str = f'на {hrs} ч.'

        return {
            'id': self.id, 'epic_id': self.epic_id,
            'epic_name': self.epic.name,
            'epic_color': self.epic.color,
            'project_id': self.epic.project_id,
            'project_name': self.epic.project.name,
            'project_color': self.epic.project.color,
            'employee_id': self.employee_id,
            'employee_name': self.employee.name,
            'employee_color': self.employee.avatar_color,
            'employee_initials': ''.join([w[0].upper() for w in self.employee.name.split()[:2]]),
            'employee_role': self.employee.role or '—',
            'title': self.title, 'description': self.description or '',
            'deadline': self.deadline.strftime('%d.%m.%Y %H:%M'),
            'deadline_raw': self.deadline.strftime('%Y-%m-%dT%H:%M:%S') + 'Z',
            'priority': self.priority,
            'priority_label': pr_label, 'priority_class': pr_class,
            'status': self.status,
            'status_label': status_label, 'status_class': status_class,
            'hours_left': round(hours_left, 1),
            'time_left_str': time_left_str,
            'created_at': self.created_at.strftime('%d.%m.%Y %H:%M')
        }


class Comment(db.Model):
    """Комментарий к эпику или задаче"""
    id = db.Column(db.Integer, primary_key=True)
    epic_id = db.Column(db.Integer, db.ForeignKey('epic.id'), nullable=True, index=True)
    task_id = db.Column(db.Integer, db.ForeignKey('task.id'), nullable=True, index=True)
    text = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(100), nullable=False)
    edited_by = db.Column(db.String(100))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        is_edited = (self.edited_by is not None and
                     self.updated_at and self.created_at and
                     (self.updated_at - self.created_at).total_seconds() > 1)
        return {
            'id': self.id,
            'epic_id': self.epic_id,
            'task_id': self.task_id,
            'text': self.text,
            'author': self.author,
            'edited_by': self.edited_by,
            'created_at': self.created_at.strftime('%d.%m.%Y %H:%M'),
            'created_at_iso': self.created_at.isoformat(),
            'updated_at': self.updated_at.strftime('%d.%m.%Y %H:%M') if self.updated_at else None,
            'is_edited': is_edited,
            'author_initials': ''.join([w[0].upper() for w in self.author.split()[:2]]) or '?'
        }


# ==================== HTML ====================

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <title>🎯 Project Manager Pro</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.0/font/bootstrap-icons.css" rel="stylesheet">
    <style>
        :root {
            --primary: #6366f1; --primary-dark: #4f46e5;
            --success: #10b981; --warning: #f59e0b; --danger: #ef4444;
            --bg: #f8fafc; --card-bg: #ffffff;
            --text: #1e293b; --text-muted: #64748b; --border: #e2e8f0;
        }
        * { box-sizing: border-box; }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8f0 100%);
            color: var(--text); min-height: 100vh; padding-bottom: 40px;
        }
        .navbar-custom {
            background: linear-gradient(135deg, #6366f1 0%, #8b5cf6 100%);
            box-shadow: 0 4px 20px rgba(99, 102, 241, 0.3); padding: 1rem 2rem;
        }
        .navbar-custom .navbar-brand { color: white; font-weight: 700; font-size: 1.4rem; }
        .navbar-custom .nav-info { color: rgba(255,255,255,0.9); font-size: 0.9rem; }

        .project-selector {
            background: var(--card-bg); border-radius: 16px; padding: 1rem 1.5rem;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid var(--border);
            margin-top: -25px; position: relative; z-index: 10;
        }
        .project-chip {
            display: inline-flex; align-items: center; gap: 0.5rem;
            padding: 0.5rem 1rem; border-radius: 10px; background: #f1f5f9;
            border: 2px solid transparent; cursor: pointer; transition: all 0.2s;
            margin-right: 0.5rem; margin-bottom: 0.3rem; font-weight: 500;
        }
        .project-chip:hover { background: #e2e8f0; }
        .project-chip.active { background: white; border-color: var(--primary); box-shadow: 0 4px 12px rgba(99, 102, 241, 0.2); }
        .project-dot { width: 12px; height: 12px; border-radius: 50%; display: inline-block; }

        .stats-card {
            background: var(--card-bg); border-radius: 16px; padding: 1.3rem;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid var(--border); transition: transform 0.2s;
        }
        .stats-card:hover { transform: translateY(-4px); box-shadow: 0 8px 24px rgba(0,0,0,0.1); }
        .stats-icon { width: 48px; height: 48px; border-radius: 12px; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; margin-bottom: 0.8rem; }
        .stats-value { font-size: 1.9rem; font-weight: 700; margin: 0; line-height: 1; }
        .stats-label { color: var(--text-muted); font-size: 0.85rem; margin-top: 0.3rem; }

        .section-card {
            background: var(--card-bg); border-radius: 16px; padding: 1.5rem;
            box-shadow: 0 2px 12px rgba(0,0,0,0.06); border: 1px solid var(--border); margin-top: 1.5rem;
        }
        .section-title { font-weight: 700; font-size: 1.25rem; margin-bottom: 1.2rem; display: flex; align-items: center; gap: 0.6rem; }

        .nav-tabs-custom { border-bottom: 2px solid var(--border); margin-bottom: 1.5rem; gap: 0.5rem; }
        .nav-tabs-custom .nav-link { border: none; color: var(--text-muted); font-weight: 600; padding: 0.8rem 1.3rem; border-radius: 10px 10px 0 0; transition: all 0.2s; }
        .nav-tabs-custom .nav-link:hover { color: var(--primary); background: #f1f5f9; }
        .nav-tabs-custom .nav-link.active { color: var(--primary); background: transparent; border-bottom: 3px solid var(--primary); }

        .team-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr)); gap: 1rem; }
        .team-card {
            background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px;
            padding: 1.2rem; transition: all 0.2s; cursor: pointer;
        }
        .team-card:hover { border-color: var(--primary); box-shadow: 0 6px 18px rgba(99, 102, 241, 0.15); transform: translateY(-2px); }
        .team-header { display: flex; align-items: center; gap: 0.9rem; margin-bottom: 1rem; }
        .avatar { width: 52px; height: 52px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: white; font-weight: 700; font-size: 1.1rem; flex-shrink: 0; }
        .avatar-sm { width: 28px; height: 28px; font-size: 0.75rem; }
        .avatar-xs { width: 32px; height: 32px; font-size: 0.8rem; }
        .team-stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin-top: 0.8rem; }
        .team-stat { text-align: center; padding: 0.5rem; background: #f8fafc; border-radius: 8px; }
        .team-stat-value { font-weight: 700; font-size: 1.1rem; }
        .team-stat-label { font-size: 0.75rem; color: var(--text-muted); }
        .workload-bar { height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; margin-top: 0.8rem; }
        .workload-fill { height: 100%; background: linear-gradient(90deg, var(--success), var(--warning), var(--danger)); transition: width 0.5s; }

        .epic-card {
            background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px;
            padding: 1.2rem; margin-bottom: 0.8rem; transition: all 0.2s;
            border-left: 4px solid var(--primary); cursor: pointer;
        }
        .epic-card:hover { box-shadow: 0 4px 14px rgba(0,0,0,0.08); }
        .epic-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.8rem; }
        .epic-title { font-weight: 700; font-size: 1.05rem; margin: 0; }
        .epic-meta { font-size: 0.85rem; color: var(--text-muted); margin-top: 0.2rem; }
        .epic-desc-preview {
            font-size: 0.85rem; color: var(--text-muted); margin-bottom: 0.5rem;
            white-space: pre-wrap; word-break: break-word;
            display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
        }
        .progress-custom { height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; margin-top: 0.5rem; }
        .progress-fill { height: 100%; background: linear-gradient(90deg, var(--primary), var(--success)); transition: width 0.5s; }

        .task-row {
            background: var(--card-bg); border: 1px solid var(--border); border-radius: 12px;
            padding: 1rem 1.2rem; margin-bottom: 0.7rem;
            display: grid; grid-template-columns: 1fr auto auto auto;
            gap: 1rem; align-items: center; transition: all 0.2s; cursor: pointer;
        }
        .task-row:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.08); }
        .task-row.overdue { border-left: 4px solid var(--danger); background: #fef2f2; }
        .task-row.warning { border-left: 4px solid var(--warning); background: #fffbeb; }
        .task-row.active { border-left: 4px solid var(--success); }
        .task-row.checked { border-left: 4px solid #94a3b8; opacity: 0.7; }
        .task-title { font-weight: 600; margin: 0 0 0.2rem 0; }
        .task-meta { font-size: 0.85rem; color: var(--text-muted); display: flex; flex-wrap: wrap; gap: 0.5rem; }
        .task-meta-item { display: inline-flex; align-items: center; gap: 0.25rem; }

        .status-badge { padding: 0.35rem 0.8rem; border-radius: 20px; font-size: 0.8rem; font-weight: 600; white-space: nowrap; }
        .status-badge.overdue { background: #fee2e2; color: #991b1b; }
        .status-badge.warning { background: #fef3c7; color: #92400e; }
        .status-badge.active { background: #d1fae5; color: #065f46; }
        .status-badge.checked { background: #e2e8f0; color: #475569; }

        .priority-badge { padding: 0.25rem 0.6rem; border-radius: 6px; font-size: 0.75rem; font-weight: 600; }
        .priority-badge.high { background: #fee2e2; color: #991b1b; }
        .priority-badge.medium { background: #fef3c7; color: #92400e; }
        .priority-badge.low { background: #dbeafe; color: #1e40af; }

        .btn-primary-custom {
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            border: none; color: white; font-weight: 600; padding: 0.55rem 1.2rem; border-radius: 10px; transition: all 0.2s;
        }
        .btn-primary-custom:hover { transform: translateY(-2px); box-shadow: 0 6px 16px rgba(99, 102, 241, 0.4); color: white; }
        .form-control, .form-select { border-radius: 10px; border: 1px solid var(--border); padding: 0.55rem 0.85rem; }
        .form-control:focus, .form-select:focus { border-color: var(--primary); box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15); }

        .btn-icon {
            width: 34px; height: 34px; border-radius: 9px;
            display: inline-flex; align-items: center; justify-content: center;
            border: 1px solid var(--border); background: white; color: var(--text-muted); cursor: pointer; transition: all 0.2s;
        }
        .btn-icon:hover { background: var(--primary); color: white; border-color: var(--primary); }

        .empty-state { text-align: center; padding: 2.5rem 1rem; color: var(--text-muted); }
        .empty-state i { font-size: 3rem; opacity: 0.3; margin-bottom: 1rem; display: block; }

        .toast-container { position: fixed; top: 90px; right: 20px; z-index: 9999; display: flex; flex-direction: column; gap: 10px; max-width: 400px; }
        .custom-toast {
            background: white; border-left: 4px solid var(--danger); border-radius: 12px; padding: 1rem 1.2rem;
            box-shadow: 0 10px 30px rgba(0,0,0,0.15); animation: slideIn 0.4s ease-out;
            display: flex; gap: 0.8rem; align-items: flex-start;
        }
        .custom-toast.success { border-left-color: var(--success); }
        .custom-toast.warning { border-left-color: var(--warning); }
        .toast-icon { font-size: 1.5rem; flex-shrink: 0; }
        .toast-content h6 { margin: 0 0 0.2rem 0; font-weight: 700; }
        .toast-content p { margin: 0; font-size: 0.9rem; color: var(--text-muted); }
        @keyframes slideIn { from { transform: translateX(400px); opacity: 0; } to { transform: translateX(0); opacity: 1; } }
        @keyframes slideOut { from { transform: translateX(0); opacity: 1; } to { transform: translateX(400px); opacity: 0; } }

        .modal-content { border-radius: 16px; border: none; }
        .modal-header { border-bottom: 1px solid var(--border); padding: 1.2rem 1.5rem; }
        .modal-body { padding: 1.5rem; max-height: 75vh; overflow-y: auto; }
        .modal-footer { border-top: 1px solid var(--border); padding: 1rem 1.5rem; }

        .filter-bar { display: flex; gap: 0.8rem; flex-wrap: wrap; margin-bottom: 1rem; }
        .filter-bar select { min-width: 180px; }

        .chip-actions { display: inline-flex; gap: 0.2rem; margin-left: 0.3rem; }
        .chip-action-btn {
            width: 22px; height: 22px; border-radius: 6px;
            display: inline-flex; align-items: center; justify-content: center;
            background: rgba(0,0,0,0.05); border: none; cursor: pointer; color: var(--text-muted); font-size: 0.75rem; transition: all 0.2s;
        }
        .chip-action-btn:hover { background: var(--primary); color: white; }

        .detail-section { margin-bottom: 1.2rem; }
        .detail-label { font-size: 0.8rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.5px; font-weight: 600; margin-bottom: 0.3rem; }
        .detail-value { font-size: 1rem; }
        .detail-description {
            white-space: pre-wrap; word-break: break-word;
            background: #f8fafc; border: 1px solid var(--border); border-radius: 10px;
            padding: 1rem; font-size: 0.95rem; line-height: 1.6; min-height: 60px;
        }
        .detail-task-list { list-style: none; padding: 0; margin: 0; }
        .detail-task-item {
            display: flex; align-items: center; gap: 0.8rem;
            padding: 0.6rem 0.8rem; border-radius: 8px; margin-bottom: 0.4rem;
            background: #f8fafc; border: 1px solid var(--border); transition: all 0.2s;
        }
        .detail-task-item:hover { background: #f1f5f9; }
        .detail-epic-item {
            display: flex; align-items: center; gap: 0.8rem;
            padding: 0.6rem 0.8rem; border-radius: 8px; margin-bottom: 0.4rem;
            background: #f8fafc; border: 1px solid var(--border); cursor: pointer; transition: all 0.2s;
        }
        .detail-epic-item:hover { background: #f1f5f9; }
        .detail-stat-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(120px, 1fr)); gap: 0.8rem; margin-bottom: 1.2rem; }
        .detail-stat-box { text-align: center; padding: 0.8rem; background: #f8fafc; border-radius: 10px; border: 1px solid var(--border); }
        .detail-stat-box .val { font-size: 1.5rem; font-weight: 700; }
        .detail-stat-box .lbl { font-size: 0.8rem; color: var(--text-muted); }

        /* Комментарии */
        .comments-section {
            border-top: 1px solid var(--border);
            padding-top: 1.2rem;
            margin-top: 1.2rem;
        }
        .comments-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            margin-bottom: 1rem;
        }
        .comments-title {
            font-weight: 700;
            font-size: 1.05rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        .comments-count {
            background: var(--primary);
            color: white;
            padding: 0.15rem 0.6rem;
            border-radius: 12px;
            font-size: 0.8rem;
            font-weight: 600;
        }
        .comment-form {
            background: #f8fafc;
            border: 1px solid var(--border);
            border-radius: 12px;
            padding: 1rem;
            margin-bottom: 1rem;
        }
        .comment-form-row {
            display: flex;
            gap: 0.6rem;
            margin-bottom: 0.6rem;
        }
        .comment-form-row input {
            flex: 0 0 180px;
        }
        .comment-form textarea {
            width: 100%;
            min-height: 70px;
            resize: vertical;
            border-radius: 10px;
            border: 1px solid var(--border);
            padding: 0.6rem 0.85rem;
            font-family: inherit;
            font-size: 0.95rem;
        }
        .comment-form textarea:focus {
            outline: none;
            border-color: var(--primary);
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
        }
        .comment-form-actions {
            display: flex;
            justify-content: flex-end;
            gap: 0.5rem;
            margin-top: 0.6rem;
        }
        .btn-sm-custom {
            padding: 0.4rem 0.9rem;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-sm-primary {
            background: var(--primary);
            color: white;
        }
        .btn-sm-primary:hover {
            background: var(--primary-dark);
        }
        .btn-sm-light {
            background: white;
            color: var(--text-muted);
            border: 1px solid var(--border);
        }
        .btn-sm-light:hover {
            background: #f1f5f9;
        }

        .comment-item {
            display: flex;
            gap: 0.8rem;
            padding: 0.9rem;
            border-radius: 10px;
            background: #f8fafc;
            border: 1px solid var(--border);
            margin-bottom: 0.6rem;
            transition: all 0.2s;
        }
        .comment-item:hover {
            background: #f1f5f9;
        }
        .comment-item.edited {
            border-left: 3px solid var(--warning);
        }
        .comment-avatar {
            width: 36px;
            height: 36px;
            border-radius: 50%;
            background: linear-gradient(135deg, var(--primary) 0%, var(--primary-dark) 100%);
            color: white;
            display: flex;
            align-items: center;
            justify-content: center;
            font-weight: 700;
            font-size: 0.85rem;
            flex-shrink: 0;
        }
        .comment-body {
            flex: 1;
            min-width: 0;
        }
        .comment-header {
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 0.3rem;
            flex-wrap: wrap;
        }
        .comment-author {
            font-weight: 600;
            font-size: 0.9rem;
        }
        .comment-date {
            font-size: 0.75rem;
            color: var(--text-muted);
        }
        .comment-edited-badge {
            font-size: 0.7rem;
            color: var(--warning);
            font-style: italic;
        }
        .comment-text {
            font-size: 0.95rem;
            line-height: 1.5;
            white-space: pre-wrap;
            word-break: break-word;
            margin: 0.2rem 0;
        }
        .comment-actions {
            display: flex;
            gap: 0.3rem;
            margin-top: 0.4rem;
        }
        .comment-action-btn {
            background: transparent;
            border: none;
            color: var(--text-muted);
            font-size: 0.75rem;
            padding: 0.2rem 0.5rem;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
            display: inline-flex;
            align-items: center;
            gap: 0.25rem;
        }
        .comment-action-btn:hover {
            background: white;
            color: var(--primary);
        }
        .comment-action-btn.delete:hover {
            color: var(--danger);
        }
        .comment-edit-area {
            width: 100%;
            min-height: 60px;
            border-radius: 8px;
            border: 1px solid var(--primary);
            padding: 0.5rem 0.75rem;
            font-family: inherit;
            font-size: 0.95rem;
            resize: vertical;
            background: white;
        }
        .comment-edit-area:focus {
            outline: none;
            box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
        }
        .no-comments {
            text-align: center;
            padding: 1.5rem 1rem;
            color: var(--text-muted);
            font-size: 0.9rem;
        }
    </style>
</head>
<body>

<nav class="navbar-custom">
    <div class="container-fluid d-flex justify-content-between align-items-center">
        <div>
            <span class="navbar-brand">🎯 Project Manager Pro</span>
            <span class="nav-info ms-3 d-none d-md-inline">Проекты • Эпики • Задачи</span>
        </div>
        <div class="nav-info"><i class="bi bi-clock"></i> <span id="currentTime"></span></div>
    </div>
</nav>

<div class="container mt-4">
    <div class="project-selector">
        <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-2">
            <div><strong><i class="bi bi-folder-fill" style="color:var(--primary);"></i> Проекты</strong></div>
            <button class="btn btn-sm btn-primary-custom" onclick="openProjectModal()"><i class="bi bi-plus-lg"></i> Новый проект</button>
        </div>
        <div id="projectsList"></div>
    </div>

    <div class="row g-3 mt-2">
        <div class="col-md-3 col-6"><div class="stats-card"><div class="stats-icon" style="background:#ede9fe;color:#6366f1;"><i class="bi bi-diagram-3-fill"></i></div><h3 class="stats-value" id="statEpics">0</h3><div class="stats-label">Эпиков</div></div></div>
        <div class="col-md-3 col-6"><div class="stats-card"><div class="stats-icon" style="background:#dbeafe;color:#3b82f6;"><i class="bi bi-list-task"></i></div><h3 class="stats-value" id="statTasks">0</h3><div class="stats-label">Задач всего</div></div></div>
        <div class="col-md-3 col-6"><div class="stats-card"><div class="stats-icon" style="background:#fee2e2;color:#ef4444;"><i class="bi bi-exclamation-triangle-fill"></i></div><h3 class="stats-value" id="statOverdue">0</h3><div class="stats-label">Просрочено</div></div></div>
        <div class="col-md-3 col-6"><div class="stats-card"><div class="stats-icon" style="background:#d1fae5;color:#10b981;"><i class="bi bi-check2-circle"></i></div><h3 class="stats-value" id="statProgress">0%</h3><div class="stats-label">Выполнено</div></div></div>
    </div>

    <ul class="nav nav-tabs nav-tabs-custom mt-4" id="mainTabs">
        <li class="nav-item"><button class="nav-link active" data-tab="team"><i class="bi bi-people-fill"></i> Команда</button></li>
        <li class="nav-item"><button class="nav-link" data-tab="epics"><i class="bi bi-layers-fill"></i> Эпики</button></li>
        <li class="nav-item"><button class="nav-link" data-tab="tasks"><i class="bi bi-kanban-fill"></i> Задачи</button></li>
    </ul>

    <div class="tab-content-pane" id="tab-team">
        <div class="section-card">
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
                <h4 class="section-title mb-0"><i class="bi bi-people-fill" style="color:var(--primary);"></i> Команда проекта</h4>
                <button class="btn btn-primary-custom" onclick="openEmployeeModal()"><i class="bi bi-person-plus-fill"></i> Добавить сотрудника</button>
            </div>
            <div id="teamList" class="team-grid"></div>
        </div>
    </div>

    <div class="tab-content-pane" id="tab-epics" style="display:none;">
        <div class="section-card">
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
                <h4 class="section-title mb-0"><i class="bi bi-layers-fill" style="color:var(--primary);"></i> Эпики проекта</h4>
                <button class="btn btn-primary-custom" onclick="openEpicModal()"><i class="bi bi-plus-lg"></i> Создать эпик</button>
            </div>
            <div id="epicsList"></div>
        </div>
    </div>

    <div class="tab-content-pane" id="tab-tasks" style="display:none;">
        <div class="section-card">
            <div class="d-flex justify-content-between align-items-center flex-wrap gap-2 mb-3">
                <h4 class="section-title mb-0"><i class="bi bi-kanban-fill" style="color:var(--primary);"></i> Задачи</h4>
                <button class="btn btn-primary-custom" onclick="openTaskModal()"><i class="bi bi-plus-lg"></i> Назначить задачу</button>
            </div>
            <div class="filter-bar">
                <select class="form-select" id="filterEpic" onchange="loadTasks()"><option value="">Все эпики</option></select>
                <select class="form-select" id="filterEmployee" onchange="loadTasks()"><option value="">Все сотрудники</option></select>
                <select class="form-select" id="filterStatus" onchange="loadTasks()">
                    <option value="">Все статусы</option>
                    <option value="active">🟢 В срок</option>
                    <option value="warning">🟡 Менее суток</option>
                    <option value="overdue">🔴 Просрочено</option>
                    <option value="checked">✅ Выполнено</option>
                </select>
            </div>
            <div id="tasksList"></div>
        </div>
    </div>
</div>

<div class="toast-container" id="toastContainer"></div>

<!-- ===== МОДАЛКА ПРОЕКТА ===== -->
<div class="modal fade" id="projectModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title fw-bold" id="projectModalTitle"><i class="bi bi-folder-plus" style="color:var(--primary);"></i> Новый проект</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <form id="projectForm"><input type="hidden" name="project_id" id="projectId">
        <div class="modal-body">
            <div class="mb-3"><label class="form-label fw-semibold">Название *</label><input type="text" class="form-control" name="name" id="projectName" required></div>
            <div class="mb-3"><label class="form-label fw-semibold">Описание</label><textarea class="form-control" name="description" id="projectDescription" rows="2"></textarea></div>
            <div class="mb-3"><label class="form-label fw-semibold">Цвет</label><input type="color" class="form-control form-control-color" name="color" id="projectColor" value="#6366f1"></div>
        </div>
        <div class="modal-footer"><button type="button" class="btn btn-light" data-bs-dismiss="modal">Отмена</button><button type="submit" class="btn btn-primary-custom" id="projectSubmitBtn">Создать</button></div>
    </form>
</div></div></div>

<!-- ===== МОДАЛКА СОТРУДНИКА ===== -->
<div class="modal fade" id="employeeModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title fw-bold" id="employeeModalTitle"><i class="bi bi-person-plus-fill" style="color:var(--primary);"></i> Новый сотрудник</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <form id="employeeForm"><input type="hidden" name="employee_id" id="employeeId">
        <div class="modal-body">
            <div class="mb-3"><label class="form-label fw-semibold">ФИО *</label><input type="text" class="form-control" name="name" id="employeeName" required></div>
            <div class="mb-3"><label class="form-label fw-semibold">Должность</label><input type="text" class="form-control" name="role" id="employeeRole"></div>
            <div class="mb-3"><label class="form-label fw-semibold">Email</label><input type="email" class="form-control" name="email" id="employeeEmail"></div>
            <div class="mb-3"><label class="form-label fw-semibold">Цвет аватара</label><input type="color" class="form-control form-control-color" name="avatar_color" id="employeeAvatarColor" value="#6366f1"></div>
        </div>
        <div class="modal-footer"><button type="button" class="btn btn-light" data-bs-dismiss="modal">Отмена</button><button type="submit" class="btn btn-primary-custom" id="employeeSubmitBtn">Добавить</button></div>
    </form>
</div></div></div>

<!-- ===== МОДАЛКА ЭПИКА ===== -->
<div class="modal fade" id="epicModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title fw-bold" id="epicModalTitle"><i class="bi bi-layers" style="color:var(--primary);"></i> Новый эпик</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <form id="epicForm"><input type="hidden" name="epic_id" id="epicId">
        <div class="modal-body">
            <div class="mb-3"><label class="form-label fw-semibold">Название *</label><input type="text" class="form-control" name="name" id="epicName" required></div>
            <div class="mb-3"><label class="form-label fw-semibold">Описание</label><textarea class="form-control" name="description" id="epicDescription" rows="3"></textarea></div>
            <div class="mb-3"><label class="form-label fw-semibold">Цвет</label><input type="color" class="form-control form-control-color" name="color" id="epicColor" value="#8b5cf6"></div>
        </div>
        <div class="modal-footer"><button type="button" class="btn btn-light" data-bs-dismiss="modal">Отмена</button><button type="submit" class="btn btn-primary-custom" id="epicSubmitBtn">Создать</button></div>
    </form>
</div></div></div>

<!-- ===== МОДАЛКА ЗАДАЧИ ===== -->
<div class="modal fade" id="taskModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered modal-lg"><div class="modal-content">
    <div class="modal-header"><h5 class="modal-title fw-bold" id="taskModalTitle"><i class="bi bi-calendar-check-fill" style="color:var(--primary);"></i> Новая задача</h5><button type="button" class="btn-close" data-bs-dismiss="modal"></button></div>
    <form id="taskForm"><input type="hidden" name="task_id" id="taskId">
        <div class="modal-body">
            <div class="mb-3"><label class="form-label fw-semibold">Название *</label><input type="text" class="form-control" name="title" id="taskTitle" required></div>
            <div class="mb-3"><label class="form-label fw-semibold">Описание</label><textarea class="form-control" name="description" id="taskDescription" rows="2"></textarea></div>
            <div class="row">
                <div class="col-md-6 mb-3"><label class="form-label fw-semibold">Проект *</label><select class="form-select" name="project_id" id="taskProjectSelect" required onchange="loadEpicsForTask()"></select></div>
                <div class="col-md-6 mb-3"><label class="form-label fw-semibold">Эпик *</label><select class="form-select" name="epic_id" id="taskEpicSelect" required></select></div>
            </div>
            <div class="row">
                <div class="col-md-6 mb-3"><label class="form-label fw-semibold">Ответственный *</label><select class="form-select" name="employee_id" id="taskEmployeeSelect" required></select></div>
                <div class="col-md-6 mb-3"><label class="form-label fw-semibold">Приоритет</label><select class="form-select" name="priority" id="taskPriority"><option value="low">🔵 Низкий</option><option value="medium" selected>🟡 Средний</option><option value="high">🔴 Высокий</option></select></div>
            </div>
            <div class="mb-3"><label class="form-label fw-semibold">Срок *</label><input type="datetime-local" class="form-control" name="deadline" id="taskDeadline" required></div>
        </div>
        <div class="modal-footer"><button type="button" class="btn btn-light" data-bs-dismiss="modal">Отмена</button><button type="submit" class="btn btn-primary-custom" id="taskSubmitBtn">Назначить</button></div>
    </form>
</div></div></div>

<!-- ===== МОДАЛКА ДЕТАЛЕЙ ===== -->
<div class="modal fade" id="detailModal" tabindex="-1"><div class="modal-dialog modal-dialog-centered modal-lg"><div class="modal-content">
    <div class="modal-header">
        <h5 class="modal-title fw-bold" id="detailModalTitle"></h5>
        <div class="d-flex gap-2">
            <span id="detailModalActions"></span>
            <button type="button" class="btn-close" data-bs-dismiss="modal"></button>
        </div>
    </div>
    <div class="modal-body" id="detailModalBody"></div>
</div></div></div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
    let currentProjectId = null;
    let seenOverdueIds = new Set();
    let allProjects = [];
    let allEmployees = [];

    // ===== localStorage для имени автора комментариев =====
    function getCommentAuthor() {
        return localStorage.getItem('comment_author') || '';
    }
    function setCommentAuthor(name) {
        localStorage.setItem('comment_author', name);
    }

    function updateClock() {
        document.getElementById('currentTime').textContent =
            new Date().toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
    }
    setInterval(updateClock, 1000); updateClock();

    function showToast(title, message, type='danger') {
        const c = document.getElementById('toastContainer');
        const icons = {danger:'🚨',warning:'⚠️',success:'✅'};
        const t = document.createElement('div');
        t.className = `custom-toast ${type}`;
        t.innerHTML = `<div class="toast-icon">${icons[type]}</div><div class="toast-content"><h6>${title}</h6><p>${message}</p></div>`;
        c.appendChild(t);
        setTimeout(() => { t.style.animation='slideOut 0.4s ease-out forwards'; setTimeout(()=>t.remove(),400); }, 7000);
    }

    function escHtml(s) { const d=document.createElement('div'); d.textContent=s||''; return d.innerHTML; }

    document.querySelectorAll('#mainTabs .nav-link').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('#mainTabs .nav-link').forEach(b=>b.classList.remove('active'));
            btn.classList.add('active');
            document.querySelectorAll('.tab-content-pane').forEach(p=>p.style.display='none');
            document.getElementById('tab-'+btn.dataset.tab).style.display='block';
        });
    });

    // ===== ПРОЕКТЫ =====
    async function loadProjects() {
        const res = await fetch('/api/projects'); allProjects = await res.json();
        const list = document.getElementById('projectsList');
        if (!allProjects.length) { list.innerHTML='<div class="text-muted"><i>Нет проектов</i></div>'; currentProjectId=null; clearDashboard(); return; }
        if (!currentProjectId || !allProjects.find(p=>p.id===currentProjectId)) currentProjectId = allProjects[0].id;
        list.innerHTML = allProjects.map(p => `
            <span class="project-chip ${p.id===currentProjectId?'active':''}" onclick="selectProject(${p.id})">
                <span class="project-dot" style="background:${p.color};"></span> ${escHtml(p.name)}
                <small class="text-muted ms-1">(${p.tasks_done}/${p.tasks_total})</small>
                <span class="chip-actions">
                    <button class="chip-action-btn" onclick="event.stopPropagation();showProjectDetail(${p.id})" title="Подробнее"><i class="bi bi-eye-fill"></i></button>
                    <button class="chip-action-btn" onclick="event.stopPropagation();openEditProjectModal(${p.id})" title="Редактировать"><i class="bi bi-pencil-fill"></i></button>
                    <button class="chip-action-btn" onclick="event.stopPropagation();deleteProject(${p.id})" title="Удалить"><i class="bi bi-x"></i></button>
                </span>
            </span>`).join('');
        await loadProjectData();
    }
    async function selectProject(id) { currentProjectId=id; await loadProjects(); }
    function clearDashboard() {
        ['statEpics','statTasks','statOverdue'].forEach(id=>document.getElementById(id).textContent='0');
        document.getElementById('statProgress').textContent='0%';
        ['teamList','epicsList','tasksList'].forEach(id=>{document.getElementById(id).innerHTML=`<div class="empty-state"><i class="bi bi-folder2-open"></i><p>Сначала создайте проект</p></div>`;});
    }
    function openProjectModal() {
        document.getElementById('projectForm').reset(); document.getElementById('projectId').value='';
        document.getElementById('projectColor').value='#6366f1';
        document.getElementById('projectModalTitle').innerHTML='<i class="bi bi-folder-plus" style="color:var(--primary);"></i> Новый проект';
        document.getElementById('projectSubmitBtn').textContent='Создать';
        new bootstrap.Modal(document.getElementById('projectModal')).show();
    }
    async function openEditProjectModal(id) {
        const r=await fetch(`/api/projects/${id}`); const p=await r.json();
        document.getElementById('projectId').value=p.id; document.getElementById('projectName').value=p.name;
        document.getElementById('projectDescription').value=p.description; document.getElementById('projectColor').value=p.color;
        document.getElementById('projectModalTitle').innerHTML='<i class="bi bi-pencil-fill" style="color:var(--primary);"></i> Редактирование';
        document.getElementById('projectSubmitBtn').textContent='Сохранить';
        new bootstrap.Modal(document.getElementById('projectModal')).show();
    }
    async function deleteProject(id) { if(!confirm('Удалить проект?'))return; await fetch(`/api/projects/${id}`,{method:'DELETE'}); currentProjectId=null; await loadProjects(); }
    document.getElementById('projectForm').addEventListener('submit', async(e)=>{
        e.preventDefault(); const d=Object.fromEntries(new FormData(e.target)); const pid=d.project_id; delete d.project_id;
        if(pid){await fetch(`/api/projects/${pid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});showToast('✅','Проект обновлён','success');}
        else{await fetch('/api/projects',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});showToast('✅','Проект создан','success');}
        bootstrap.Modal.getInstance(document.getElementById('projectModal')).hide(); await loadProjects();
    });

    async function loadProjectData() { if(!currentProjectId)return; await loadTeam(); await loadEpics(); await loadTasks(); await loadStats(); }
    async function loadStats() {
        const r=await fetch(`/api/projects/${currentProjectId}/stats`); const d=await r.json();
        document.getElementById('statEpics').textContent=d.epics; document.getElementById('statTasks').textContent=d.tasks_total;
        document.getElementById('statOverdue').textContent=d.tasks_overdue; document.getElementById('statProgress').textContent=d.progress+'%';
        d.overdue_tasks.forEach(t=>{if(!seenOverdueIds.has(t.id)){seenOverdueIds.add(t.id);showToast('⏰ Срок истёк!',`«${t.title}» (${t.employee_name})`,'danger');}});
    }

    // ===== СОТРУДНИКИ =====
    async function loadTeam() {
        const r=await fetch('/api/employees'); allEmployees=await r.json();
        const rp=await fetch(`/api/employees?project_id=${currentProjectId}`); const data=await rp.json();
        const list=document.getElementById('teamList');
        if(!data.length){list.innerHTML=`<div class="empty-state" style="grid-column:1/-1;"><i class="bi bi-people"></i><p>Нет сотрудников</p></div>`;return;}
        list.innerHTML=data.map(e=>`
            <div class="team-card" onclick="showEmployeeDetail(${e.id})">
                <div class="team-header">
                    <div class="avatar" style="background:${e.avatar_color};">${e.initials}</div>
                    <div class="flex-grow-1"><h6 class="mb-0 fw-bold">${escHtml(e.name)}</h6><small class="text-muted">${escHtml(e.role)}</small>
                    ${e.email!=='—'?`<div><small class="text-muted"><i class="bi bi-envelope"></i> ${escHtml(e.email)}</small></div>`:''}</div>
                    <button class="btn-icon" onclick="event.stopPropagation();openEditEmployeeModal(${e.id})" title="Редактировать"><i class="bi bi-pencil"></i></button>
                    <button class="btn-icon" onclick="event.stopPropagation();deleteEmployee(${e.id})" title="Удалить"><i class="bi bi-trash"></i></button>
                </div>
                <div class="team-stats">
                    <div class="team-stat"><div class="team-stat-value" style="color:var(--primary);">${e.tasks_active}</div><div class="team-stat-label">В работе</div></div>
                    <div class="team-stat"><div class="team-stat-value" style="color:var(--danger);">${e.tasks_overdue}</div><div class="team-stat-label">Просрочено</div></div>
                    <div class="team-stat"><div class="team-stat-value" style="color:var(--success);">${e.tasks_done}</div><div class="team-stat-label">Выполнено</div></div>
                </div>
                <div class="workload-bar"><div class="workload-fill" style="width:${e.workload}%;"></div></div>
                <small class="text-muted d-block mt-1">Загрузка: ${e.workload}%</small>
            </div>`).join('');
    }
    function openEmployeeModal() {
        document.getElementById('employeeForm').reset(); document.getElementById('employeeId').value='';
        document.getElementById('employeeAvatarColor').value='#6366f1';
        document.getElementById('employeeModalTitle').innerHTML='<i class="bi bi-person-plus-fill" style="color:var(--primary);"></i> Новый сотрудник';
        document.getElementById('employeeSubmitBtn').textContent='Добавить';
        new bootstrap.Modal(document.getElementById('employeeModal')).show();
    }
    async function openEditEmployeeModal(id) {
        const r=await fetch(`/api/employees/${id}`); const e=await r.json();
        document.getElementById('employeeId').value=e.id; document.getElementById('employeeName').value=e.name;
        document.getElementById('employeeRole').value=e.role==='—'?'':e.role;
        document.getElementById('employeeEmail').value=e.email==='—'?'':e.email;
        document.getElementById('employeeAvatarColor').value=e.avatar_color;
        document.getElementById('employeeModalTitle').innerHTML='<i class="bi bi-person-gear" style="color:var(--primary);"></i> Редактирование';
        document.getElementById('employeeSubmitBtn').textContent='Сохранить';
        new bootstrap.Modal(document.getElementById('employeeModal')).show();
    }
    async function deleteEmployee(id) { if(!confirm('Удалить сотрудника?'))return; await fetch(`/api/employees/${id}`,{method:'DELETE'}); await loadTeam(); await loadEpics(); await loadTasks(); }
    document.getElementById('employeeForm').addEventListener('submit', async(e)=>{
        e.preventDefault(); const d=Object.fromEntries(new FormData(e.target)); const eid=d.employee_id; delete d.employee_id;
        if(eid){await fetch(`/api/employees/${eid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});showToast('✅','Сотрудник обновлён','success');}
        else{await fetch('/api/employees',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});showToast('✅','Сотрудник добавлен','success');}
        bootstrap.Modal.getInstance(document.getElementById('employeeModal')).hide(); await loadTeam(); await loadTasks();
    });

    // ===== ЭПИКИ =====
    async function loadEpics() {
        const r=await fetch(`/api/epics?project_id=${currentProjectId}`); const data=await r.json();
        const list=document.getElementById('epicsList');
        document.getElementById('filterEpic').innerHTML='<option value="">Все эпики</option>'+data.map(e=>`<option value="${e.id}">${escHtml(e.name)}</option>`).join('');
        if(!data.length){list.innerHTML=`<div class="empty-state"><i class="bi bi-layers"></i><p>Нет эпиков</p></div>`;return;}
        list.innerHTML=data.map(e=>`
            <div class="epic-card" style="border-left-color:${e.color};" onclick="showEpicDetail(${e.id})">
                <div class="epic-header">
                    <div>
                        <h6 class="epic-title">${escHtml(e.name)}</h6>
                        <div class="epic-meta">📋 Задач: <b>${e.tasks_total}</b> • ✅ Выполнено: <b>${e.tasks_done}</b>${e.tasks_overdue>0?` • <span style="color:var(--danger);">🔴 ${e.tasks_overdue}</span>`:''}</div>
                    </div>
                    <div class="d-flex gap-1">
                        <button class="btn-icon" onclick="event.stopPropagation();openTaskModal(null,${e.id})" title="Добавить задачу"><i class="bi bi-plus"></i></button>
                        <button class="btn-icon" onclick="event.stopPropagation();openEditEpicModal(${e.id})" title="Редактировать"><i class="bi bi-pencil"></i></button>
                        <button class="btn-icon" onclick="event.stopPropagation();deleteEpic(${e.id})" title="Удалить"><i class="bi bi-trash"></i></button>
                    </div>
                </div>
                ${e.description?`<div class="epic-desc-preview">${escHtml(e.description)}</div>`:''}
                <div class="d-flex justify-content-between align-items-center"><small class="fw-semibold">Прогресс: ${e.progress}%</small><small class="text-muted">${e.created_at}</small></div>
                <div class="progress-custom"><div class="progress-fill" style="width:${e.progress}%;"></div></div>
            </div>`).join('');
    }
    function openEpicModal() {
        document.getElementById('epicForm').reset(); document.getElementById('epicId').value='';
        document.getElementById('epicColor').value='#8b5cf6';
        document.getElementById('epicModalTitle').innerHTML='<i class="bi bi-layers" style="color:var(--primary);"></i> Новый эпик';
        document.getElementById('epicSubmitBtn').textContent='Создать';
        new bootstrap.Modal(document.getElementById('epicModal')).show();
    }
    async function openEditEpicModal(id) {
        const r=await fetch(`/api/epics/${id}`); const e=await r.json();
        document.getElementById('epicId').value=e.id; document.getElementById('epicName').value=e.name;
        document.getElementById('epicDescription').value=e.description; document.getElementById('epicColor').value=e.color;
        document.getElementById('epicModalTitle').innerHTML='<i class="bi bi-pencil-fill" style="color:var(--primary);"></i> Редактирование эпика';
        document.getElementById('epicSubmitBtn').textContent='Сохранить';
        new bootstrap.Modal(document.getElementById('epicModal')).show();
    }
    async function deleteEpic(id) { if(!confirm('Удалить эпик?'))return; await fetch(`/api/epics/${id}`,{method:'DELETE'}); await loadEpics(); await loadStats(); }
    document.getElementById('epicForm').addEventListener('submit', async(e)=>{
        e.preventDefault(); const d=Object.fromEntries(new FormData(e.target)); const eid=d.epic_id; delete d.epic_id;
        if(eid){await fetch(`/api/epics/${eid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});showToast('✅','Эпик обновлён','success');}
        else{d.project_id=currentProjectId;await fetch('/api/epics',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});showToast('✅','Эпик создан','success');}
        bootstrap.Modal.getInstance(document.getElementById('epicModal')).hide(); await loadEpics(); await loadStats();
    });

    // ===== ЗАДАЧИ =====
    async function loadTasks() {
        if(!currentProjectId)return;
        const eId=document.getElementById('filterEpic').value, empId=document.getElementById('filterEmployee').value, st=document.getElementById('filterStatus').value;
        let url=`/api/tasks?project_id=${currentProjectId}`;
        if(eId)url+=`&epic_id=${eId}`; if(empId)url+=`&employee_id=${empId}`; if(st)url+=`&status=${st}`;
        const r=await fetch(url); const data=await r.json(); const list=document.getElementById('tasksList');
        const er=await fetch('/api/employees'); const emps=await er.json();
        const fe=document.getElementById('filterEmployee'); const cv=fe.value;
        fe.innerHTML='<option value="">Все сотрудники</option>'+emps.map(e=>`<option value="${e.id}">${escHtml(e.name)}</option>`).join(''); fe.value=cv;
        if(!data.length){list.innerHTML=`<div class="empty-state"><i class="bi bi-clipboard"></i><p>Задач не найдено</p></div>`;return;}
        const order={overdue:0,warning:1,active:2,checked:3};
        data.sort((a,b)=>order[a.status_class]!==order[b.status_class]?order[a.status_class]-order[b.status_class]:new Date(a.deadline_raw)-new Date(b.deadline_raw));
        list.innerHTML=data.map(t=>`
            <div class="task-row ${t.status_class}" onclick="showTaskDetail(${t.id})">
                <div>
                    <div class="task-title">${escHtml(t.title)}</div>
                    <div class="task-meta">
                        <span class="task-meta-item"><span class="avatar avatar-sm" style="background:${t.employee_color};">${t.employee_initials}</span> ${escHtml(t.employee_name)}</span>
                        <span class="task-meta-item"><span class="project-dot" style="background:${t.project_color};"></span> ${escHtml(t.epic_name)}</span>
                        <span class="priority-badge ${t.priority_class}">${t.priority_label}</span>
                    </div>
                </div>
                <div class="text-end">
                    <div class="fw-semibold small">📅 ${t.deadline}</div>
                    <small class="text-muted">${t.hours_left>0?'осталось '+t.time_left_str:'просрочено '+t.time_left_str}</small>
                </div>
                <div><span class="status-badge ${t.status_class}">${t.status_label}</span></div>
                <div class="d-flex gap-1">
                    ${t.status!=='checked'?`<button class="btn-icon" onclick="event.stopPropagation();markCompleted(${t.id})" title="Выполнено"><i class="bi bi-check-lg"></i></button>`:''}
                    <button class="btn-icon" onclick="event.stopPropagation();openEditTaskModal(${t.id})" title="Редактировать"><i class="bi bi-pencil"></i></button>
                    <button class="btn-icon" onclick="event.stopPropagation();deleteTask(${t.id})" title="Удалить"><i class="bi bi-trash"></i></button>
                </div>
            </div>`).join('');
    }
    async function loadEpicsForTask() {
        const pid=document.getElementById('taskProjectSelect').value; const es=document.getElementById('taskEpicSelect');
        if(!pid){es.innerHTML='<option value="">— Сначала проект —</option>';return;}
        const r=await fetch(`/api/epics?project_id=${pid}`); const eps=await r.json();
        es.innerHTML=eps.length?'<option value="">— Эпик —</option>'+eps.map(e=>`<option value="${e.id}">${escHtml(e.name)}</option>`).join(''):'<option value="">— Нет эпиков —</option>';
    }
    function openTaskModal(projectId=null,epicId=null) {
        document.getElementById('taskForm').reset(); document.getElementById('taskId').value='';
        document.getElementById('taskModalTitle').innerHTML='<i class="bi bi-calendar-check-fill" style="color:var(--primary);"></i> Новая задача';
        document.getElementById('taskSubmitBtn').textContent='Назначить';
        document.getElementById('taskProjectSelect').innerHTML='<option value="">— Проект —</option>'+allProjects.map(p=>`<option value="${p.id}" ${p.id===(projectId||currentProjectId)?'selected':''}>${escHtml(p.name)}</option>`).join('');
        document.getElementById('taskEmployeeSelect').innerHTML='<option value="">— Сотрудник —</option>'+allEmployees.map(e=>`<option value="${e.id}">${escHtml(e.name)}</option>`).join('');
        loadEpicsForTask().then(()=>{if(epicId)document.getElementById('taskEpicSelect').value=epicId;});
        new bootstrap.Modal(document.getElementById('taskModal')).show();
    }
    async function openEditTaskModal(taskId) {
        const r=await fetch(`/api/tasks/${taskId}`); const t=await r.json();
        document.getElementById('taskId').value=t.id; document.getElementById('taskTitle').value=t.title;
        document.getElementById('taskDescription').value=t.description; document.getElementById('taskPriority').value=t.priority;
        const dl = new Date(t.deadline_raw);
        const local = new Date(dl.getTime() - dl.getTimezoneOffset()*60000).toISOString().slice(0,16);
        document.getElementById('taskDeadline').value = local;
        document.getElementById('taskModalTitle').innerHTML='<i class="bi bi-pencil-fill" style="color:var(--primary);"></i> Редактирование';
        document.getElementById('taskSubmitBtn').textContent='Сохранить';
        document.getElementById('taskProjectSelect').innerHTML='<option value="">— Проект —</option>'+allProjects.map(p=>`<option value="${p.id}" ${p.id===t.project_id?'selected':''}>${escHtml(p.name)}</option>`).join('');
        document.getElementById('taskEmployeeSelect').innerHTML='<option value="">— Сотрудник —</option>'+allEmployees.map(e=>`<option value="${e.id}" ${e.id===t.employee_id?'selected':''}>${escHtml(e.name)}</option>`).join('');
        await loadEpicsForTask(); document.getElementById('taskEpicSelect').value=t.epic_id;
        new bootstrap.Modal(document.getElementById('taskModal')).show();
    }
    document.getElementById('taskForm').addEventListener('submit', async(e)=>{
        e.preventDefault(); const d=Object.fromEntries(new FormData(e.target)); const tid=d.task_id; delete d.task_id;
        const localDate = new Date(d.deadline);
        d.deadline = new Date(localDate.getTime() - localDate.getTimezoneOffset()*60000).toISOString().slice(0,19);
        if(tid){await fetch(`/api/tasks/${tid}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});showToast('✅','Задача обновлена','success');}
        else{await fetch('/api/tasks',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(d)});showToast('✅','Задача создана','success');}
        bootstrap.Modal.getInstance(document.getElementById('taskModal')).hide(); await loadTasks(); await loadEpics(); await loadStats(); await loadTeam();
    });
    async function markCompleted(id) { await fetch(`/api/tasks/${id}/check`,{method:'POST'}); await loadTasks(); await loadEpics(); await loadStats(); await loadTeam(); showToast('✅ Выполнено','Задача выполнена','success'); }
    async function deleteTask(id) { if(!confirm('Удалить?'))return; await fetch(`/api/tasks/${id}`,{method:'DELETE'}); await loadTasks(); await loadEpics(); await loadStats(); await loadTeam(); }

    // ===== КОММЕНТАРИИ =====

    // Рендер блока комментариев (вызывается из showEpicDetail/showTaskDetail)
    function renderCommentsBlock(entityType, entityId, comments) {
        const savedAuthor = getCommentAuthor();
        const commentsHtml = comments.length ? comments.map(c => `
            <div class="comment-item ${c.is_edited?'edited':''}" id="comment-${c.id}">
                <div class="comment-avatar">${escHtml(c.author_initials)}</div>
                <div class="comment-body">
                    <div class="comment-header">
                        <span class="comment-author">${escHtml(c.author)}</span>
                        <span class="comment-date">• ${c.created_at}</span>
                        ${c.is_edited ? `<span class="comment-edited-badge" title="Изменено: ${escHtml(c.edited_by||'')} ${c.updated_at||''}">✏️ изменено${c.edited_by ? ' '+escHtml(c.edited_by) : ''}</span>` : ''}
                    </div>
                    <div class="comment-text" id="comment-text-${c.id}">${escHtml(c.text)}</div>
                    <div class="comment-actions">
                        <button class="comment-action-btn" onclick="startEditComment(${c.id}, '${entityType}', ${entityId})">
                            <i class="bi bi-pencil"></i> Редактировать
                        </button>
                        <button class="comment-action-btn delete" onclick="deleteComment(${c.id}, '${entityType}', ${entityId})">
                            <i class="bi bi-trash"></i> Удалить
                        </button>
                    </div>
                </div>
            </div>
        `).join('') : '<div class="no-comments"><i class="bi bi-chat-dots"></i> Комментариев пока нет. Будьте первым!</div>';

        return `
            <div class="comments-section">
                <div class="comments-header">
                    <div class="comments-title">
                        <i class="bi bi-chat-dots-fill" style="color:var(--primary);"></i>
                        Комментарии
                        <span class="comments-count">${comments.length}</span>
                    </div>
                </div>
                <div class="comment-form">
                    <div class="comment-form-row">
                        <input type="text" class="form-control" id="commentAuthor-${entityType}-${entityId}"
                               placeholder="Ваше имя" value="${escHtml(savedAuthor)}">
                    </div>
                    <textarea id="commentText-${entityType}-${entityId}" placeholder="Напишите комментарий..."></textarea>
                    <div class="comment-form-actions">
                        <button class="btn-sm-custom btn-sm-primary" onclick="addComment('${entityType}', ${entityId})">
                            <i class="bi bi-send"></i> Отправить
                        </button>
                    </div>
                </div>
                <div id="commentsList-${entityType}-${entityId}">
                    ${commentsHtml}
                </div>
            </div>
        `;
    }

    // Загрузка комментариев
    async function loadComments(entityType, entityId) {
        const r = await fetch(`/api/${entityType}/${entityId}/comments`);
        return await r.json();
    }

    // Добавление комментария
    async function addComment(entityType, entityId) {
        const authorInput = document.getElementById(`commentAuthor-${entityType}-${entityId}`);
        const textInput = document.getElementById(`commentText-${entityType}-${entityId}`);
        const author = authorInput.value.trim();
        const text = textInput.value.trim();

        if (!author) { showToast('⚠️', 'Введите ваше имя', 'warning'); authorInput.focus(); return; }
        if (!text) { showToast('⚠️', 'Введите текст комментария', 'warning'); textInput.focus(); return; }

        setCommentAuthor(author);

        await fetch(`/api/${entityType}/${entityId}/comments`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ author, text })
        });

        // Перерисовываем блок комментариев
        const comments = await loadComments(entityType, entityId);
        document.getElementById(`commentsList-${entityType}-${entityId}`).innerHTML =
            comments.map(c => renderSingleComment(c, entityType, entityId)).join('');
        // Обновляем счётчик
        const countEl = document.querySelector(`#commentsList-${entityType}-${entityId}`).parentElement.querySelector('.comments-count');
        if (countEl) countEl.textContent = comments.length;

        textInput.value = '';
        showToast('✅', 'Комментарий добавлен', 'success');
    }

    // Рендер одного комментария
    function renderSingleComment(c, entityType, entityId) {
        return `
            <div class="comment-item ${c.is_edited?'edited':''}" id="comment-${c.id}">
                <div class="comment-avatar">${escHtml(c.author_initials)}</div>
                <div class="comment-body">
                    <div class="comment-header">
                        <span class="comment-author">${escHtml(c.author)}</span>
                        <span class="comment-date">• ${c.created_at}</span>
                        ${c.is_edited ? `<span class="comment-edited-badge" title="Изменено: ${escHtml(c.edited_by||'')} ${c.updated_at||''}">✏️ изменено${c.edited_by ? ' '+escHtml(c.edited_by) : ''}</span>` : ''}
                    </div>
                    <div class="comment-text" id="comment-text-${c.id}">${escHtml(c.text)}</div>
                    <div class="comment-actions">
                        <button class="comment-action-btn" onclick="startEditComment(${c.id}, '${entityType}', ${entityId})">
                            <i class="bi bi-pencil"></i> Редактировать
                        </button>
                        <button class="comment-action-btn delete" onclick="deleteComment(${c.id}, '${entityType}', ${entityId})">
                            <i class="bi bi-trash"></i> Удалить
                        </button>
                    </div>
                </div>
            </div>
        `;
    }

    // Inline-редактирование комментария
    async function startEditComment(commentId, entityType, entityId) {
        const r = await fetch(`/api/comments/${commentId}`);
        const c = await r.json();

        const item = document.getElementById(`comment-${commentId}`);
        const textEl = document.getElementById(`comment-text-${commentId}`);
        const actionsEl = item.querySelector('.comment-actions');

        // Сохраняем оригинальное содержимое для отмены
        const originalText = textEl.innerHTML;
        const originalActions = actionsEl.innerHTML;

        // Заменяем текст на textarea
        textEl.outerHTML = `<textarea class="comment-edit-area" id="comment-edit-${commentId}">${escHtml(c.text)}</textarea>`;

        // Заменяем кнопки на "Сохранить" / "Отмена"
        actionsEl.innerHTML = `
            <button class="comment-action-btn" onclick="saveEditComment(${commentId}, '${entityType}', ${entityId})" style="color:var(--success);font-weight:600;">
                <i class="bi bi-check-lg"></i> Сохранить
            </button>
            <button class="comment-action-btn" onclick="cancelEditComment(${commentId}, '${entityType}', ${entityId})">
                <i class="bi bi-x-lg"></i> Отмена
            </button>
        `;

        // Сохраняем оригиналы в data-атрибутах для отмены
        item.dataset.originalText = c.text;
        item.dataset.originalActions = originalActions;

        const textarea = document.getElementById(`comment-edit-${commentId}`);
        textarea.focus();
        textarea.setSelectionRange(textarea.value.length, textarea.value.length);
    }

    async function saveEditComment(commentId, entityType, entityId) {
        const textarea = document.getElementById(`comment-edit-${commentId}`);
        const newText = textarea.value.trim();
        if (!newText) { showToast('⚠️', 'Комментарий не может быть пустым', 'warning'); return; }

        const editor = getCommentAuthor() || 'Аноним';

        await fetch(`/api/comments/${commentId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: newText, edited_by: editor })
        });

        // Перерисовываем весь список комментариев
        const comments = await loadComments(entityType, entityId);
        document.getElementById(`commentsList-${entityType}-${entityId}`).innerHTML =
            comments.map(c => renderSingleComment(c, entityType, entityId)).join('');
        const countEl = document.querySelector(`#commentsList-${entityType}-${entityId}`).parentElement.querySelector('.comments-count');
        if (countEl) countEl.textContent = comments.length;

        showToast('✅', 'Комментарий обновлён', 'success');
    }

    function cancelEditComment(commentId, entityType, entityId) {
        const item = document.getElementById(`comment-${commentId}`);
        const textEl = document.getElementById(`comment-edit-${commentId}`);
        const originalText = item.dataset.originalText;
        const originalActions = item.dataset.originalActions;

        // Восстанавливаем текст
        textEl.outerHTML = `<div class="comment-text" id="comment-text-${commentId}">${escHtml(originalText)}</div>`;
        // Восстанавливаем кнопки
        item.querySelector('.comment-actions').innerHTML = originalActions;
    }

    async function deleteComment(commentId, entityType, entityId) {
        if (!confirm('Удалить комментарий?')) return;
        await fetch(`/api/comments/${commentId}`, { method: 'DELETE' });

        const comments = await loadComments(entityType, entityId);
        document.getElementById(`commentsList-${entityType}-${entityId}`).innerHTML =
            comments.length ? comments.map(c => renderSingleComment(c, entityType, entityId)).join('')
                            : '<div class="no-comments"><i class="bi bi-chat-dots"></i> Комментариев пока нет. Будьте первым!</div>';
        const countEl = document.querySelector(`#commentsList-${entityType}-${entityId}`).parentElement.querySelector('.comments-count');
        if (countEl) countEl.textContent = comments.length;

        showToast('🗑️', 'Комментарий удалён', 'success');
    }

    // ===== КАРТОЧКИ ДЕТАЛЕЙ =====

    async function showProjectDetail(id) {
        const r=await fetch(`/api/projects/${id}`); const p=await r.json();
        const er=await fetch(`/api/epics?project_id=${id}`); const epics=await er.json();
        document.getElementById('detailModalTitle').innerHTML=`<span class="project-dot" style="background:${p.color};"></span> ${escHtml(p.name)}`;
        document.getElementById('detailModalActions').innerHTML=`<button class="btn-icon" onclick="bootstrap.Modal.getInstance(document.getElementById('detailModal')).hide();openEditProjectModal(${p.id})"><i class="bi bi-pencil"></i></button>`;
        document.getElementById('detailModalBody').innerHTML=`
            <div class="detail-stat-grid">
                <div class="detail-stat-box"><div class="val" style="color:var(--primary);">${p.epics_count}</div><div class="lbl">Эпиков</div></div>
                <div class="detail-stat-box"><div class="val" style="color:#3b82f6;">${p.tasks_total}</div><div class="lbl">Задач</div></div>
                <div class="detail-stat-box"><div class="val" style="color:var(--success);">${p.tasks_done}</div><div class="lbl">Выполнено</div></div>
                <div class="detail-stat-box"><div class="val">${p.progress}%</div><div class="lbl">Прогресс</div></div>
            </div>
            ${p.description?`<div class="detail-section"><div class="detail-label">Описание</div><div class="detail-description">${escHtml(p.description)}</div></div>`:''}
            <div class="detail-section"><div class="detail-label">Эпики (${epics.length})</div>
                ${epics.length?`<div class="detail-task-list">${epics.map(e=>`
                    <div class="detail-epic-item" onclick="bootstrap.Modal.getInstance(document.getElementById('detailModal')).hide();setTimeout(()=>showEpicDetail(${e.id}),300)">
                        <span class="project-dot" style="background:${e.color};width:16px;height:16px;"></span>
                        <div class="flex-grow-1"><strong>${escHtml(e.name)}</strong><br><small class="text-muted">${e.tasks_done}/${e.tasks_total} задач • ${e.progress}%</small></div>
                        <div class="progress-custom" style="width:80px;margin:0;"><div class="progress-fill" style="width:${e.progress}%;"></div></div>
                    </div>`).join('')}</div>`:'<p class="text-muted">Нет эпиков</p>'}
            </div>
            <div class="detail-section"><small class="text-muted">Создан: ${p.created_at}</small></div>`;
        new bootstrap.Modal(document.getElementById('detailModal')).show();
    }

    async function showEmployeeDetail(id) {
        const r=await fetch(`/api/employees/${id}`); const emp=await r.json();
        const tr=await fetch(`/api/tasks?project_id=${currentProjectId}&employee_id=${id}`); const tasks=await tr.json();
        document.getElementById('detailModalTitle').innerHTML=`<span class="avatar avatar-sm" style="background:${emp.avatar_color};">${emp.initials}</span> ${escHtml(emp.name)}`;
        document.getElementById('detailModalActions').innerHTML=`<button class="btn-icon" onclick="bootstrap.Modal.getInstance(document.getElementById('detailModal')).hide();openEditEmployeeModal(${emp.id})"><i class="bi bi-pencil"></i></button>`;
        document.getElementById('detailModalBody').innerHTML=`
            <div class="detail-stat-grid">
                <div class="detail-stat-box"><div class="val" style="color:var(--primary);">${emp.tasks_active}</div><div class="lbl">В работе</div></div>
                <div class="detail-stat-box"><div class="val" style="color:var(--danger);">${emp.tasks_overdue}</div><div class="lbl">Просрочено</div></div>
                <div class="detail-stat-box"><div class="val" style="color:var(--success);">${emp.tasks_done}</div><div class="lbl">Выполнено</div></div>
                <div class="detail-stat-box"><div class="val">${emp.workload}%</div><div class="lbl">Загрузка</div></div>
            </div>
            <div class="row mb-3">
                <div class="col-6"><div class="detail-label">Должность</div><div class="detail-value">${escHtml(emp.role)}</div></div>
                <div class="col-6"><div class="detail-label">Email</div><div class="detail-value">${escHtml(emp.email)}</div></div>
            </div>
            <div class="detail-section"><div class="detail-label">Задачи в проекте (${tasks.length})</div>
                ${tasks.length?`<ul class="detail-task-list">${tasks.map(t=>`
                    <li class="detail-task-item">
                        <span class="status-badge ${t.status_class}" style="font-size:0.7rem;">${t.status_label}</span>
                        <div class="flex-grow-1"><strong>${escHtml(t.title)}</strong><br><small class="text-muted">${escHtml(t.epic_name)} • 📅 ${t.deadline}</small></div>
                        <span class="priority-badge ${t.priority_class}">${t.priority_label}</span>
                    </li>`).join('')}</ul>`:'<p class="text-muted">Нет задач в этом проекте</p>'}
            </div>
            <div class="detail-section"><small class="text-muted">Добавлен: ${emp.created_at}</small></div>`;
        new bootstrap.Modal(document.getElementById('detailModal')).show();
    }

    async function showEpicDetail(id) {
        const r=await fetch(`/api/epics/${id}`); const e=await r.json();
        const tr=await fetch(`/api/tasks?epic_id=${id}`); const tasks=await tr.json();
        const comments = await loadComments('epics', id);

        document.getElementById('detailModalTitle').innerHTML=`<span class="project-dot" style="background:${e.color};width:16px;height:16px;"></span> ${escHtml(e.name)}`;
        document.getElementById('detailModalActions').innerHTML=`<button class="btn-icon" onclick="bootstrap.Modal.getInstance(document.getElementById('detailModal')).hide();openEditEpicModal(${e.id})"><i class="bi bi-pencil"></i></button>`;
        document.getElementById('detailModalBody').innerHTML=`
            <div class="detail-stat-grid">
                <div class="detail-stat-box"><div class="val" style="color:#3b82f6;">${e.tasks_total}</div><div class="lbl">Задач</div></div>
                <div class="detail-stat-box"><div class="val" style="color:var(--success);">${e.tasks_done}</div><div class="lbl">Выполнено</div></div>
                <div class="detail-stat-box"><div class="val" style="color:var(--danger);">${e.tasks_overdue}</div><div class="lbl">Просрочено</div></div>
                <div class="detail-stat-box"><div class="val">${e.progress}%</div><div class="lbl">Прогресс</div></div>
            </div>
            <div class="row mb-3">
                <div class="col-6"><div class="detail-label">Проект</div><div class="detail-value"><span class="project-dot" style="background:${e.project_color};"></span> ${escHtml(e.project_name)}</div></div>
                <div class="col-6"><div class="detail-label">Создан</div><div class="detail-value">${e.created_at}</div></div>
            </div>
            ${e.description?`<div class="detail-section"><div class="detail-label">Описание</div><div class="detail-description">${escHtml(e.description)}</div></div>`:''}
            <div class="detail-section"><div class="detail-label">Задачи (${tasks.length})</div>
                ${tasks.length?`<ul class="detail-task-list">${tasks.map(t=>`
                    <li class="detail-task-item" style="cursor:pointer;" onclick="bootstrap.Modal.getInstance(document.getElementById('detailModal')).hide();setTimeout(()=>showTaskDetail(${t.id}),300)">
                        <span class="status-badge ${t.status_class}" style="font-size:0.7rem;">${t.status_label}</span>
                        <div class="flex-grow-1"><strong>${escHtml(t.title)}</strong><br><small class="text-muted">👤 ${escHtml(t.employee_name)} • 📅 ${t.deadline}</small></div>
                        <span class="priority-badge ${t.priority_class}">${t.priority_label}</span>
                    </li>`).join('')}</ul>`:'<p class="text-muted">Нет задач</p>'}
            </div>
            ${renderCommentsBlock('epics', id, comments)}`;
        new bootstrap.Modal(document.getElementById('detailModal')).show();
    }

    async function showTaskDetail(id) {
        const r=await fetch(`/api/tasks/${id}`); const t=await r.json();
        const comments = await loadComments('tasks', id);

        document.getElementById('detailModalTitle').innerHTML=`${escHtml(t.title)}`;
        document.getElementById('detailModalActions').innerHTML=`<button class="btn-icon" onclick="bootstrap.Modal.getInstance(document.getElementById('detailModal')).hide();openEditTaskModal(${t.id})"><i class="bi bi-pencil"></i></button>`;
        const deadlineDate = new Date(t.deadline_raw);
        const localStr = deadlineDate.toLocaleString('ru-RU', {day:'2-digit',month:'2-digit',year:'numeric',hour:'2-digit',minute:'2-digit'});
        document.getElementById('detailModalBody').innerHTML=`
            <div class="d-flex gap-2 mb-3 flex-wrap">
                <span class="status-badge ${t.status_class}">${t.status_label}</span>
                <span class="priority-badge ${t.priority_class}">${t.priority_label}</span>
            </div>
            <div class="detail-stat-grid">
                <div class="detail-stat-box"><div class="val" style="color:${t.hours_left>0?'var(--success)':'var(--danger)'};">${t.hours_left>0?'⏳':'⚠️'}</div><div class="lbl">${t.hours_left>0?'Осталось '+t.time_left_str:'Просрочено '+t.time_left_str}</div></div>
                <div class="detail-stat-box"><div class="val" style="font-size:1rem;">${localStr}</div><div class="lbl">Дедлайн</div></div>
            </div>
            <div class="row mb-3">
                <div class="col-6"><div class="detail-label">Ответственный</div><div class="detail-value d-flex align-items-center gap-2"><span class="avatar avatar-sm" style="background:${t.employee_color};">${t.employee_initials}</span><div><strong>${escHtml(t.employee_name)}</strong><br><small class="text-muted">${escHtml(t.employee_role)}</small></div></div></div>
                <div class="col-6"><div class="detail-label">Проект / Эпик</div><div class="detail-value"><span class="project-dot" style="background:${t.project_color};"></span> ${escHtml(t.project_name)}<br><span class="project-dot" style="background:${t.epic_color};"></span> ${escHtml(t.epic_name)}</div></div>
            </div>
            ${t.description?`<div class="detail-section"><div class="detail-label">Описание</div><div class="detail-description">${escHtml(t.description)}</div></div>`:'<div class="detail-section"><div class="detail-label">Описание</div><div class="detail-description text-muted">Нет описания</div></div>'}
            <div class="detail-section"><small class="text-muted">Создана: ${t.created_at}</small></div>
            ${renderCommentsBlock('tasks', id, comments)}`;
        new bootstrap.Modal(document.getElementById('detailModal')).show();
    }

    // ===== INIT =====
    async function init() {
        const [pr,er]=await Promise.all([fetch('/api/projects'),fetch('/api/employees')]);
        allProjects=await pr.json(); allEmployees=await er.json(); await loadProjects();
    }
    init();
    setInterval(()=>{if(currentProjectId)loadProjectData();},30000);
</script>
</body>
</html>
"""


# ==================== МАРШРУТЫ ====================

@app.route('/')
def index():
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/projects', methods=['GET'])
def get_projects():
    return jsonify([p.to_dict() for p in Project.query.order_by(Project.created_at.desc()).all()])

@app.route('/api/projects/<int:id>', methods=['GET'])
def get_project(id):
    return jsonify(Project.query.get_or_404(id).to_dict())

@app.route('/api/projects', methods=['POST'])
def create_project():
    d = request.json
    p = Project(name=d['name'], description=d.get('description'), color=d.get('color','#6366f1'))
    db.session.add(p); db.session.commit()
    return jsonify(p.to_dict()), 201

@app.route('/api/projects/<int:id>', methods=['PUT'])
def update_project(id):
    p = Project.query.get_or_404(id); d = request.json
    p.name = d.get('name', p.name); p.description = d.get('description', p.description); p.color = d.get('color', p.color)
    db.session.commit(); return jsonify(p.to_dict())

@app.route('/api/projects/<int:id>/stats', methods=['GET'])
def project_stats(id):
    p = Project.query.get_or_404(id); now = datetime.utcnow()
    Task.query.filter(Task.deadline < now, Task.status == 'active').update({'status': 'overdue'}); db.session.commit()
    at = [t for e in p.epics for t in e.tasks]; ot = [t for t in at if t.status == 'overdue']
    done = sum(1 for t in at if t.status == 'checked'); total = len(at)
    return jsonify({'epics': len(p.epics), 'tasks_total': total, 'tasks_overdue': len(ot), 'tasks_done': done,
        'progress': round(done/total*100) if total else 0,
        'overdue_tasks': [{'id':t.id,'title':t.title,'employee_name':t.employee.name} for t in ot if not t.reminder_sent]})

@app.route('/api/projects/<int:id>', methods=['DELETE'])
def delete_project(id):
    p = Project.query.get_or_404(id); db.session.delete(p); db.session.commit(); return '', 204

@app.route('/api/employees', methods=['GET'])
def get_employees():
    pid = request.args.get('project_id', type=int)
    return jsonify([e.to_dict(project_id=pid) for e in Employee.query.order_by(Employee.name).all()])

@app.route('/api/employees/<int:id>', methods=['GET'])
def get_employee(id):
    return jsonify(Employee.query.get_or_404(id).to_dict())

@app.route('/api/employees', methods=['POST'])
def create_employee():
    d = request.json
    e = Employee(name=d['name'], role=d.get('role'), email=d.get('email'), avatar_color=d.get('avatar_color','#6366f1'))
    db.session.add(e); db.session.commit(); return jsonify(e.to_dict()), 201

@app.route('/api/employees/<int:id>', methods=['PUT'])
def update_employee(id):
    e = Employee.query.get_or_404(id); d = request.json
    e.name = d.get('name', e.name); e.role = d.get('role', e.role)
    e.email = d.get('email', e.email); e.avatar_color = d.get('avatar_color', e.avatar_color)
    db.session.commit(); return jsonify(e.to_dict())

@app.route('/api/employees/<int:id>', methods=['DELETE'])
def delete_employee(id):
    e = Employee.query.get_or_404(id); Task.query.filter_by(employee_id=id).delete(); db.session.delete(e); db.session.commit(); return '', 204

@app.route('/api/epics', methods=['GET'])
def get_epics():
    pid = request.args.get('project_id', type=int); q = Epic.query
    if pid: q = q.filter_by(project_id=pid)
    return jsonify([e.to_dict() for e in q.order_by(Epic.created_at.desc()).all()])

@app.route('/api/epics/<int:id>', methods=['GET'])
def get_epic(id):
    return jsonify(Epic.query.get_or_404(id).to_dict())

@app.route('/api/epics', methods=['POST'])
def create_epic():
    d = request.json
    e = Epic(project_id=d['project_id'], name=d['name'], description=d.get('description'), color=d.get('color','#8b5cf6'))
    db.session.add(e); db.session.commit(); return jsonify(e.to_dict()), 201

@app.route('/api/epics/<int:id>', methods=['PUT'])
def update_epic(id):
    e = Epic.query.get_or_404(id); d = request.json
    e.name = d.get('name', e.name); e.description = d.get('description', e.description); e.color = d.get('color', e.color)
    db.session.commit(); return jsonify(e.to_dict())

@app.route('/api/epics/<int:id>', methods=['DELETE'])
def delete_epic(id):
    e = Epic.query.get_or_404(id); db.session.delete(e); db.session.commit(); return '', 204

@app.route('/api/tasks', methods=['GET'])
def get_tasks():
    pid = request.args.get('project_id', type=int); eid = request.args.get('epic_id', type=int)
    empid = request.args.get('employee_id', type=int); st = request.args.get('status')
    now = datetime.utcnow()
    Task.query.filter(Task.deadline < now, Task.status == 'active').update({'status': 'overdue'}); db.session.commit()
    q = Task.query
    if pid: q = q.join(Epic).filter(Epic.project_id == pid)
    if eid: q = q.filter_by(epic_id=eid)
    if empid: q = q.filter_by(employee_id=empid)
    if st:
        if st == 'overdue': q = q.filter(Task.status == 'overdue')
        elif st == 'checked': q = q.filter(Task.status == 'checked')
        elif st == 'active': q = q.filter(Task.status == 'active', Task.deadline >= now)
        elif st == 'warning': q = q.filter(Task.status == 'active', Task.deadline < now + timedelta(hours=24), Task.deadline >= now)
    return jsonify([t.to_dict() for t in q.all()])

@app.route('/api/tasks/<int:id>', methods=['GET'])
def get_task(id):
    return jsonify(Task.query.get_or_404(id).to_dict())

@app.route('/api/tasks', methods=['POST'])
def create_task():
    d = request.json; dl = datetime.fromisoformat(d['deadline'].replace('Z',''))
    t = Task(epic_id=d['epic_id'], employee_id=d['employee_id'], title=d['title'], description=d.get('description'), priority=d.get('priority','medium'), deadline=dl)
    db.session.add(t); db.session.commit(); return jsonify(t.to_dict()), 201

@app.route('/api/tasks/<int:id>', methods=['PUT'])
def update_task(id):
    t = Task.query.get_or_404(id); d = request.json
    t.title = d.get('title', t.title); t.description = d.get('description', t.description)
    t.epic_id = d.get('epic_id', t.epic_id); t.employee_id = d.get('employee_id', t.employee_id)
    t.priority = d.get('priority', t.priority)
    if 'deadline' in d: t.deadline = datetime.fromisoformat(d['deadline'].replace('Z',''))
    db.session.commit(); return jsonify(t.to_dict())

@app.route('/api/tasks/<int:id>/check', methods=['POST'])
def check_task(id):
    t = Task.query.get_or_404(id); t.status = 'checked'; db.session.commit(); return jsonify(t.to_dict())

@app.route('/api/tasks/<int:id>', methods=['DELETE'])
def delete_task(id):
    t = Task.query.get_or_404(id); db.session.delete(t); db.session.commit(); return '', 204


# ==================== КОММЕНТАРИИ ====================

@app.route('/api/epics/<int:epic_id>/comments', methods=['GET'])
def get_epic_comments(epic_id):
    Epic.query.get_or_404(epic_id)
    comments = Comment.query.filter_by(epic_id=epic_id).order_by(Comment.created_at.asc()).all()
    return jsonify([c.to_dict() for c in comments])


@app.route('/api/epics/<int:epic_id>/comments', methods=['POST'])
def create_epic_comment(epic_id):
    Epic.query.get_or_404(epic_id)
    d = request.json
    if not d.get('text') or not d.get('author'):
        return jsonify({'error': 'text and author required'}), 400
    c = Comment(epic_id=epic_id, text=d['text'], author=d['author'])
    db.session.add(c); db.session.commit()
    return jsonify(c.to_dict()), 201


@app.route('/api/tasks/<int:task_id>/comments', methods=['GET'])
def get_task_comments(task_id):
    Task.query.get_or_404(task_id)
    comments = Comment.query.filter_by(task_id=task_id).order_by(Comment.created_at.asc()).all()
    return jsonify([c.to_dict() for c in comments])


@app.route('/api/tasks/<int:task_id>/comments', methods=['POST'])
def create_task_comment(task_id):
    Task.query.get_or_404(task_id)
    d = request.json
    if not d.get('text') or not d.get('author'):
        return jsonify({'error': 'text and author required'}), 400
    c = Comment(task_id=task_id, text=d['text'], author=d['author'])
    db.session.add(c); db.session.commit()
    return jsonify(c.to_dict()), 201


@app.route('/api/comments/<int:id>', methods=['GET'])
def get_comment(id):
    c = Comment.query.get_or_404(id)
    return jsonify(c.to_dict())


@app.route('/api/comments/<int:id>', methods=['PUT'])
def update_comment(id):
    c = Comment.query.get_or_404(id)
    d = request.json
    if d.get('text'):
        c.text = d['text']
    if d.get('edited_by'):
        c.edited_by = d['edited_by']
    c.updated_at = datetime.utcnow()
    db.session.commit()
    return jsonify(c.to_dict())


@app.route('/api/comments/<int:id>', methods=['DELETE'])
def delete_comment(id):
    c = Comment.query.get_or_404(id)
    db.session.delete(c); db.session.commit()
    return '', 204


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    print("\n🎯 Project Manager Pro v3.4 запущен!")
    print("📍 http://localhost:5001\n")
    app.run(debug=True, host='0.0.0.0', port=5001)