"""工作流引擎核心 — 数据结构和执行引擎"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)


class NodeType(str, Enum):
    """工作流节点类型"""
    TRIGGER = "trigger"      # 触发节点: 开始流程
    ACTION = "action"        # 动作节点: 执行操作
    CONDITION = "condition"  # 条件节点: 分支判断
    WAIT = "wait"            # 等待节点: 定时/事件等待
    END = "end"              # 结束节点: 终止流程


class WorkflowStatus(str, Enum):
    """工作流实例状态"""
    PENDING = "pending"        # 待触发
    RUNNING = "running"        # 运行中
    COMPLETED = "completed"    # 完成
    FAILED = "failed"          # 失败
    PAUSED = "paused"          # 暂停
    CANCELLED = "cancelled"    # 取消


class NodeStatus(str, Enum):
    """节点执行状态"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowNode:
    """工作流节点"""
    id: str
    type: NodeType
    label: str
    config: Dict[str, Any] = field(default_factory=dict)
    position: Dict[str, float] = field(default_factory=lambda: {"x": 0, "y": 0})
    description: str = ""


@dataclass
class WorkflowEdge:
    """工作流边 — 定义节点间流转"""
    id: str
    source_id: str
    target_id: str
    label: str = ""
    condition: Optional[str] = None  # 条件表达式，None=无条件流转


@dataclass
class WorkflowDefinition:
    """工作流定义 — DAG"""
    id: str
    name: str
    description: str = ""
    nodes: List[WorkflowNode] = field(default_factory=list)
    edges: List[WorkflowEdge] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    version: int = 1
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    
    def get_node(self, node_id: str) -> Optional[WorkflowNode]:
        return next((n for n in self.nodes if n.id == node_id), None)
    
    def get_start_nodes(self) -> List[WorkflowNode]:
        """获取所有起始节点（TRIGGER类型且没有入边的节点）"""
        targets = {e.target_id for e in self.edges}
        return [n for n in self.nodes if n.type == NodeType.TRIGGER and n.id not in targets]
    
    def get_downstream(self, node_id: str) -> List[WorkflowEdge]:
        return [e for e in self.edges if e.source_id == node_id]
    
    def get_upstream(self, node_id: str) -> List[WorkflowEdge]:
        return [e for e in self.edges if e.target_id == node_id]
    
    def validate(self) -> Tuple[bool, List[str]]:
        """验证DAG合法性"""
        errors = []
        node_ids = {n.id for n in self.nodes}
        
        # 1. 每个边引用的节点必须存在
        for e in self.edges:
            if e.source_id not in node_ids:
                errors.append(f"边 {e.id}: 源节点 {e.source_id} 不存在")
            if e.target_id not in node_ids:
                errors.append(f"边 {e.id}: 目标节点 {e.target_id} 不存在")
        
        if errors:
            return False, errors
        
        # 2. 至少有一个TRIGGER节点
        if not any(n.type == NodeType.TRIGGER for n in self.nodes):
            errors.append("缺少TRIGGER节点")
        
        # 3. 至少有一个END节点
        if not any(n.type == NodeType.END for n in self.nodes):
            errors.append("缺少END节点")
        
        # 4. 检查是否有环（拓扑排序）
        if self._has_cycle():
            errors.append("DAG检测到环路")
        
        return len(errors) == 0, errors
    
    def _has_cycle(self) -> bool:
        """检测DAG是否有环（Kahn算法）"""
        in_degree: Dict[str, int] = {n.id: 0 for n in self.nodes}
        adj: Dict[str, List[str]] = {n.id: [] for n in self.nodes}
        
        for e in self.edges:
            adj[e.source_id].append(e.target_id)
            in_degree[e.target_id] = in_degree.get(e.target_id, 0) + 1
        
        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        visited = 0
        
        while queue:
            nid = queue.pop(0)
            visited += 1
            for neighbor in adj.get(nid, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)
        
        return visited != len(self.nodes)


@dataclass
class WorkflowInstance:
    """工作流运行实例"""
    id: str
    workflow_id: str
    status: WorkflowStatus = WorkflowStatus.PENDING
    current_node_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)
    node_statuses: Dict[str, NodeStatus] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class WorkflowEngine:
    """工作流执行引擎"""
    
    def __init__(self):
        self._action_handlers: Dict[str, Callable] = {}
        self._condition_evaluators: Dict[str, Callable] = {}
    
    def register_action(self, action_type: str, handler: Callable):
        """注册动作处理器"""
        self._action_handlers[action_type] = handler
    
    def register_condition(self, condition_type: str, evaluator: Callable):
        """注册条件评估器"""
        self._condition_evaluators[condition_type] = evaluator
    
    def execute(self, definition: WorkflowDefinition, instance: WorkflowInstance) -> WorkflowInstance:
        """执行工作流实例"""
        is_valid, errors = definition.validate()
        if not is_valid:
            instance.status = WorkflowStatus.FAILED
            instance.error_message = f"DAG验证失败: {'; '.join(errors)}"
            return instance
        
        instance.status = WorkflowStatus.RUNNING
        instance.started_at = datetime.now(timezone.utc)
        
        # 找到起始节点
        start_nodes = definition.get_start_nodes()
        if not start_nodes:
            instance.status = WorkflowStatus.FAILED
            instance.error_message = "没有可用的起始节点"
            return instance
        
        try:
            for start_node in start_nodes:
                instance.current_node_id = start_node.id
                self._execute_node(definition, instance, start_node)
            
            # 检查是否所有路径都到达了END
            if instance.status == WorkflowStatus.RUNNING:
                instance.status = WorkflowStatus.COMPLETED
                instance.completed_at = datetime.now(timezone.utc)
                
        except Exception as e:
            instance.status = WorkflowStatus.FAILED
            instance.error_message = str(e)
            logger.error(f"工作流执行失败: {e}")
        
        return instance
    
    def _execute_node(self, definition: WorkflowDefinition, instance: WorkflowInstance, node: WorkflowNode):
        """执行单个节点"""
        instance.node_statuses[node.id] = NodeStatus.RUNNING
        instance.current_node_id = node.id
        
        try:
            if node.type == NodeType.ACTION:
                self._execute_action(node, instance)
            elif node.type == NodeType.CONDITION:
                self._execute_condition(definition, node, instance)
            elif node.type == NodeType.WAIT:
                self._execute_wait(node, instance)
            elif node.type == NodeType.TRIGGER:
                pass  # 触发节点本身就是被触发的，不需要执行逻辑
            elif node.type == NodeType.END:
                instance.node_statuses[node.id] = NodeStatus.COMPLETED
                return
            
            instance.node_statuses[node.id] = NodeStatus.COMPLETED
            
            # 向下游节点推进
            downstream = definition.get_downstream(node.id)
            for edge in downstream:
                if edge.condition:
                    if not self._evaluate_condition(edge.condition, instance):
                        continue
                target = definition.get_node(edge.target_id)
                if target:
                    self._execute_node(definition, instance, target)
                    
        except Exception as e:
            instance.node_statuses[node.id] = NodeStatus.FAILED
            raise
    
    def _execute_action(self, node: WorkflowNode, instance: WorkflowInstance):
        """执行动作节点"""
        action_type = node.config.get("action_type", "")
        handler = self._action_handlers.get(action_type)
        if handler:
            result = handler(node.config, instance.context)
            instance.context.update(result)
    
    def _execute_condition(self, definition: WorkflowDefinition, node: WorkflowNode, instance: WorkflowInstance):
        """执行条件节点 — 只走第一个满足条件的分支"""
        downstream = definition.get_downstream(node.id)
        for edge in downstream:
            if edge.condition:
                if self._evaluate_condition(edge.condition, instance):
                    target = definition.get_node(edge.target_id)
                    if target:
                        self._execute_node(definition, instance, target)
                    return
        # 没有满足条件的，走无条件分支
        for edge in downstream:
            if not edge.condition:
                target = definition.get_node(edge.target_id)
                if target:
                    self._execute_node(definition, instance, target)
                return
    
    def _execute_wait(self, node: WorkflowNode, instance: WorkflowInstance):
        """执行等待节点（标记为等待，不阻塞）"""
        instance.node_statuses[node.id] = NodeStatus.PENDING
        instance.status = WorkflowStatus.PAUSED
    
    def _evaluate_condition(self, condition: str, instance: WorkflowInstance) -> bool:
        """评估条件表达式"""
        # 简单条件评估：支持 context.field == value、context.field > value 等
        evaluator = self._condition_evaluators.get(condition)
        if evaluator:
            return evaluator(instance.context)
        
        # 默认：从context中取字段值比较
        if "==" in condition:
            field, value = condition.split("==", 1)
            field = field.strip()
            value = value.strip().strip("'").strip('"')
            return str(instance.context.get(field)) == value
        elif ">" in condition:
            field, value = condition.split(">", 1)
            return float(instance.context.get(field, 0)) > float(value)
        elif "<" in condition:
            field, value = condition.split("<", 1)
            return float(instance.context.get(field, 0)) < float(value)
        
        return True
