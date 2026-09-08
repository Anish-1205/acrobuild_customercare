import { useEffect, useMemo, useState } from "react";
import {
  createWorkflowRule,
  deleteWorkflowRule,
  duplicateWorkflowRule,
  getAdminTags,
  getWorkflowRuleAffectedTickets,
  getWorkflowRules,
  restoreDefaultWorkflowRule,
  updateWorkflowRule
} from "../lib/api";
import type {
  RuleAffectedTicket,
  TicketTag,
  WorkflowRule,
  WorkflowRuleCondition,
  WorkflowRuleConfig
} from "../types";

type RulesPageProps = {
  embedded?: boolean;
};

type RuleEditorTab = "settings" | "affected";
type ConditionListKey = "branch_conditions" | "trigger_conditions";
type TagListKey = "else_tag_ids" | "match_tag_ids";
type RuleMode = "business_hours" | "custom";
type FieldValueType = "none" | "number" | "select" | "text";

type RuleDraft = {
  config: WorkflowRuleConfig;
  description: string;
  id: number;
  is_enabled: boolean;
  name: string;
};

type FieldMeta = {
  label: string;
  operators: string[];
  valueType: FieldValueType;
  values?: Array<{ label: string; value: string }>;
};

const eventOptions = [
  {
    label: "ticket created",
    value: "ticket_created"
  },
  {
    label: "ticket updated",
    value: "ticket_updated"
  }
];

const operatorLabels: Record<string, string> = {
  contains: "contains",
  during_business_hours: "during business hours",
  greater_or_equal: "is greater or equal to",
  greater_than: "is greater than",
  is: "is",
  is_not: "is not",
  less_or_equal: "is less or equal to",
  less_than: "is less than",
  not_contains: "does not contain",
  outside_business_hours: "outside business hours"
};

const fieldMetaMap: Record<string, FieldMeta> = {
  assigned_agent: {
    label: "assigned agent",
    operators: ["is", "is_not", "contains", "not_contains"],
    valueType: "text"
  },
  created_at: {
    label: "created date of ticket",
    operators: ["during_business_hours", "outside_business_hours"],
    valueType: "none"
  },
  customer_email: {
    label: "customer email",
    operators: ["is", "is_not", "contains", "not_contains"],
    valueType: "text"
  },
  customer_order_count: {
    label: "customer order count",
    operators: ["greater_or_equal", "greater_than", "less_or_equal", "less_than", "is", "is_not"],
    valueType: "number"
  },
  customer_total_spent: {
    label: "customer total spent",
    operators: ["greater_or_equal", "greater_than", "less_or_equal", "less_than", "is", "is_not"],
    valueType: "number"
  },
  customer_vip: {
    label: "customer is VIP",
    operators: ["is", "is_not"],
    valueType: "select",
    values: [
      { label: "true", value: "true" },
      { label: "false", value: "false" }
    ]
  },
  issue_type: {
    label: "issue type",
    operators: ["is", "is_not", "contains", "not_contains"],
    valueType: "select",
    values: [
      { label: "Billing", value: "Billing" },
      { label: "Account", value: "Account" },
      { label: "Logistics", value: "Logistics" },
      { label: "NDIS", value: "NDIS" },
      { label: "Order", value: "Order" },
      { label: "General", value: "General" }
    ]
  },
  message_from_agent: {
    label: "message from agent",
    operators: ["is", "is_not"],
    valueType: "select",
    values: [
      { label: "true", value: "true" },
      { label: "false", value: "false" }
    ]
  },
  priority: {
    label: "priority",
    operators: ["is", "is_not"],
    valueType: "select",
    values: [
      { label: "Low", value: "Low" },
      { label: "Medium", value: "Medium" },
      { label: "High", value: "High" },
      { label: "Urgent", value: "Urgent" }
    ]
  },
  ticket_status: {
    label: "ticket status",
    operators: ["is", "is_not"],
    valueType: "select",
    values: [
      { label: "Open", value: "Open" },
      { label: "Pending", value: "Pending" },
      { label: "Closed", value: "Closed" },
      { label: "Solved", value: "Solved" }
    ]
  }
};

function createConditionId(prefix: string) {
  return `${prefix}-${Math.random().toString(36).slice(2, 9)}`;
}

function createCondition(field = "ticket_status", operator?: string, value?: string): WorkflowRuleCondition {
  const fieldMeta = fieldMetaMap[field] ?? fieldMetaMap.ticket_status;
  const nextOperator = operator ?? fieldMeta.operators[0] ?? "is";
  const nextValue =
    value ??
    (fieldMeta.valueType === "none"
      ? ""
      : fieldMeta.values?.[0]?.value ??
        (fieldMeta.valueType === "number" ? "0" : ""));

  return {
    field,
    id: createConditionId("condition"),
    operator: nextOperator,
    value: nextValue
  };
}

function buildBusinessHoursConfig(matchTagIds: number[] = [], elseTagIds: number[] = []): WorkflowRuleConfig {
  return {
    branch_conditions: [],
    else_tag_ids: elseTagIds,
    event: "ticket_created",
    match_tag_ids: matchTagIds,
    mode: "business_hours",
    trigger_conditions: [createCondition("created_at", "during_business_hours", "")],
    version: 1
  };
}

function buildCustomRuleConfig(matchTagIds: number[] = [], elseTagIds: number[] = []): WorkflowRuleConfig {
  return {
    branch_conditions: [createCondition("customer_total_spent", "greater_or_equal", "1000")],
    else_tag_ids: elseTagIds,
    event: "ticket_created",
    match_tag_ids: matchTagIds,
    mode: "custom",
    trigger_conditions: [
      createCondition("ticket_status", "is", "Open"),
      createCondition("message_from_agent", "is", "false")
    ],
    version: 1
  };
}

function buildEmptyCustomRuleConfig(): WorkflowRuleConfig {
  return {
    branch_conditions: [],
    else_tag_ids: [],
    event: "ticket_created",
    match_tag_ids: [],
    mode: "custom",
    trigger_conditions: [],
    version: 1
  };
}

function buildFreshRuleDraft(ruleId: number): RuleDraft {
  return {
    config: buildEmptyCustomRuleConfig(),
    description: "",
    id: ruleId,
    is_enabled: true,
    name: "New rule"
  };
}

function getPrimaryTagId(tagIds: number[]) {
  return tagIds[0] ?? null;
}

function normalizeTagIds(tagIds: unknown, fallback: number[] = []) {
  const values = Array.isArray(tagIds) ? tagIds : fallback;
  const uniqueIds = new Set<number>();

  return values
    .map((tagId) => Number(tagId))
    .filter((tagId) => Number.isFinite(tagId) && tagId > 0)
    .filter((tagId) => {
      if (uniqueIds.has(tagId)) {
        return false;
      }

      uniqueIds.add(tagId);
      return true;
    });
}

function normalizeCondition(condition: Partial<WorkflowRuleCondition> | undefined, index: number) {
  const field = condition?.field && fieldMetaMap[condition.field] ? condition.field : "ticket_status";
  const fieldMeta = fieldMetaMap[field];
  const operator = condition?.operator && fieldMeta.operators.includes(condition.operator)
    ? condition.operator
    : fieldMeta.operators[0];
  const nextValue =
    fieldMeta.valueType === "none"
      ? ""
      : String(
          condition?.value ??
            fieldMeta.values?.[0]?.value ??
            (fieldMeta.valueType === "number" ? "0" : "")
        );

  return {
    field,
    id: String(condition?.id || createConditionId(`condition-${index + 1}`)),
    operator,
    value: nextValue
  };
}

function normalizeRuleConfig(rule: WorkflowRule): WorkflowRuleConfig {
  const mode = (rule.config?.mode ??
    (rule.builder_mode === "business_hours" || rule.condition_operator === "during_business_hours"
      ? "business_hours"
      : "custom")) as RuleMode;
  const matchTagIds = normalizeTagIds(rule.config?.match_tag_ids, rule.match_tag_ids ?? (rule.true_tag_id ? [rule.true_tag_id] : []));
  const elseTagIds = normalizeTagIds(rule.config?.else_tag_ids, rule.else_tag_ids ?? (rule.false_tag_id ? [rule.false_tag_id] : []));
  const fallbackConfig =
    mode === "business_hours"
      ? buildBusinessHoursConfig(matchTagIds, elseTagIds)
      : buildCustomRuleConfig(matchTagIds, elseTagIds);

  const triggerConditions =
    rule.config?.trigger_conditions?.length
      ? rule.config.trigger_conditions.map((condition, index) => normalizeCondition(condition, index))
      : fallbackConfig.trigger_conditions;
  const branchConditions =
    rule.config?.branch_conditions?.length
      ? rule.config.branch_conditions.map((condition, index) => normalizeCondition(condition, index))
      : fallbackConfig.branch_conditions;

  return {
    branch_conditions: branchConditions,
    else_tag_ids: elseTagIds,
    event: rule.config?.event || rule.event_name || fallbackConfig.event,
    match_tag_ids: matchTagIds,
    mode,
    trigger_conditions: triggerConditions,
    version: 1
  };
}

function ruleToDraft(rule: WorkflowRule): RuleDraft {
  return {
    config: normalizeRuleConfig(rule),
    description: rule.description || "",
    id: rule.id,
    is_enabled: Boolean(Number(rule.is_enabled)),
    name: rule.name || "Workflow Rule"
  };
}

function formatLabel(value: string | null | undefined, fallback: string) {
  const normalized = String(value || "")
    .trim()
    .replace(/_/g, " ");

  return normalized || fallback;
}

function getOperatorLabel(operator: string) {
  return operatorLabels[operator] || formatLabel(operator, "is");
}

function getTagName(tags: TicketTag[], tagId: number | null, fallback: string) {
  if (!tagId) {
    return fallback;
  }

  return tags.find((tag) => Number(tag.id) === Number(tagId))?.name || fallback;
}

function getTagNames(tags: TicketTag[], tagIds: number[]) {
  return normalizeTagIds(tagIds).map((tagId) => ({
    id: tagId,
    name: getTagName(tags, tagId, `Tag ${tagId}`)
  }));
}

function isMethodNotAllowedError(error: unknown) {
  return error instanceof Error && error.message.toLowerCase().includes("method not allowed");
}

function getEventLabel(eventName: string) {
  return eventOptions.find((option) => option.value === eventName)?.label ?? formatLabel(eventName, "ticket event");
}

function getEventSentence(eventName: string) {
  const label = getEventLabel(eventName);

  if (label === "ticket created") {
    return "a ticket is created";
  }

  if (label === "ticket updated") {
    return "a ticket is updated";
  }

  return label;
}

function getConditionValueLabel(condition: WorkflowRuleCondition) {
  const fieldMeta = fieldMetaMap[condition.field] ?? fieldMetaMap.ticket_status;

  if (fieldMeta.valueType === "none") {
    return "";
  }

  if (fieldMeta.valueType === "select") {
    return fieldMeta.values?.find((option) => option.value === condition.value)?.label ?? condition.value;
  }

  return condition.value || "";
}

function describeCondition(condition: WorkflowRuleCondition) {
  const fieldMeta = fieldMetaMap[condition.field] ?? fieldMetaMap.ticket_status;
  const valueLabel = getConditionValueLabel(condition);
  const parts = [fieldMeta.label, getOperatorLabel(condition.operator)];

  if (valueLabel) {
    parts.push(valueLabel);
  }

  return parts.join(" ");
}

function joinWithAnd(values: string[]) {
  if (!values.length) {
    return "";
  }

  if (values.length === 1) {
    return values[0];
  }

  if (values.length === 2) {
    return `${values[0]} and ${values[1]}`;
  }

  return `${values.slice(0, -1).join(", ")}, and ${values[values.length - 1]}`;
}

function buildRulePreview(draft: RuleDraft, tags: TicketTag[]) {
  const triggerChecks = draft.config.trigger_conditions.map((condition) => describeCondition(condition));
  const branchChecks = draft.config.branch_conditions.map((condition) => describeCondition(condition));
  const yesTags = getTagNames(tags, draft.config.match_tag_ids).map((tag) => tag.name);
  const noTags = getTagNames(tags, draft.config.else_tag_ids).map((tag) => tag.name);
  const summaryParts = [`When ${getEventSentence(draft.config.event)}`];

  if (triggerChecks.length) {
    summaryParts.push(`and ${joinWithAnd(triggerChecks)}`);
  }

  if (draft.config.mode === "custom" && branchChecks.length) {
    summaryParts.push(`and ${joinWithAnd(branchChecks)}`);
  }

  const yesAction = yesTags.length
    ? `add the tag${yesTags.length === 1 ? "" : "s"} ${joinWithAnd(yesTags)}`
    : "no main action is chosen yet";
  const noAction = noTags.length
    ? `If it does not match, add ${joinWithAnd(noTags)}`
    : "If it does not match, nothing extra happens yet";

  return `${summaryParts.join(" ")}, ${yesAction}. ${noAction}.`;
}

export function RulesPage({ embedded = false }: RulesPageProps) {
  const [rules, setRules] = useState<WorkflowRule[]>([]);
  const [tags, setTags] = useState<TicketTag[]>([]);
  const [selectedRuleId, setSelectedRuleId] = useState<number | null>(null);
  const [newRuleId, setNewRuleId] = useState<number | null>(null);
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const [activeTab, setActiveTab] = useState<RuleEditorTab>("settings");
  const [affectedTickets, setAffectedTickets] = useState<RuleAffectedTicket[]>([]);
  const [isBootstrapping, setIsBootstrapping] = useState(true);
  const [isLoadingAffected, setIsLoadingAffected] = useState(false);
  const [isWorking, setIsWorking] = useState(false);
  const [error, setError] = useState("");
  const [successMessage, setSuccessMessage] = useState("");

  const selectedRule = useMemo(
    () => rules.find((rule) => Number(rule.id) === Number(selectedRuleId)) ?? null,
    [rules, selectedRuleId]
  );

  const affectedSummary = useMemo(
    () => ({
      during: affectedTickets.filter((ticket) => ticket.business_hours_tag === "Business Hours").length,
      outside: affectedTickets.filter((ticket) => ticket.business_hours_tag !== "Business Hours").length,
      total: affectedTickets.length
    }),
    [affectedTickets]
  );

  const isNewRule = Boolean(draft && newRuleId === draft.id);
  const canSaveRule = Boolean(draft?.name.trim() && draft.config.match_tag_ids.length);
  const enabledRuleCount = useMemo(
    () => rules.filter((rule) => Boolean(Number(rule.is_enabled))).length,
    [rules]
  );
  const activeCheckCount = draft
    ? draft.config.trigger_conditions.length + draft.config.branch_conditions.length
    : 0;
  const matchTags = useMemo(
    () => (draft ? getTagNames(tags, draft.config.match_tag_ids) : []),
    [draft, tags]
  );
  const elseTags = useMemo(
    () => (draft ? getTagNames(tags, draft.config.else_tag_ids) : []),
    [draft, tags]
  );
  const rulePreview = useMemo(
    () => (draft ? buildRulePreview(draft, tags) : ""),
    [draft, tags]
  );

  async function loadWorkspace(preferredRuleId?: number | null) {
    const [ruleResponse, tagResponse] = await Promise.all([
      getWorkflowRules(),
      getAdminTags()
    ]);

    const nextRules = ruleResponse.rules;
    const resolvedSelectedRule =
      nextRules.find((rule) => Number(rule.id) === Number(preferredRuleId)) ?? nextRules[0] ?? null;

    setRules(nextRules);
    setTags(tagResponse.tags);
    setSelectedRuleId(resolvedSelectedRule ? Number(resolvedSelectedRule.id) : null);
    setDraft(resolvedSelectedRule ? ruleToDraft(resolvedSelectedRule) : null);
    return resolvedSelectedRule;
  }

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      try {
        setIsBootstrapping(true);
        setError("");
        await loadWorkspace();
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load workflow rules.");
        }
      } finally {
        if (!cancelled) {
          setIsBootstrapping(false);
        }
      }
    }

    void hydrate();

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!selectedRule) {
      setDraft(null);
      return;
    }

    setDraft(ruleToDraft(selectedRule));
  }, [selectedRule]);

  useEffect(() => {
    let cancelled = false;

    async function hydrateAffectedTickets() {
      if (!selectedRuleId) {
        setAffectedTickets([]);
        return;
      }

      try {
        setIsLoadingAffected(true);
        const response = await getWorkflowRuleAffectedTickets(selectedRuleId);

        if (!cancelled) {
          setAffectedTickets(response.tickets);
        }
      } catch (loadError) {
        if (!cancelled) {
          setError(loadError instanceof Error ? loadError.message : "Unable to load affected tickets.");
        }
      } finally {
        if (!cancelled) {
          setIsLoadingAffected(false);
        }
      }
    }

    void hydrateAffectedTickets();

    return () => {
      cancelled = true;
    };
  }, [selectedRuleId]);

  function updateDraft(updater: (current: RuleDraft) => RuleDraft) {
    setDraft((current) => (current ? updater(current) : current));
  }

  function updateCondition(listKey: ConditionListKey, conditionId: string, patch: Partial<WorkflowRuleCondition>) {
    updateDraft((current) => ({
      ...current,
      config: {
        ...current.config,
        [listKey]: current.config[listKey].map((condition) => {
          if (condition.id !== conditionId) {
            return condition;
          }

          const nextField = patch.field ?? condition.field;
          const fieldMeta = fieldMetaMap[nextField] ?? fieldMetaMap.ticket_status;
          const nextOperator =
            patch.field && !fieldMeta.operators.includes(condition.operator)
              ? fieldMeta.operators[0]
              : patch.operator ?? condition.operator;
          const nextValue =
            fieldMeta.valueType === "none"
              ? ""
              : String(
                  patch.field
                    ? fieldMeta.values?.[0]?.value ?? (fieldMeta.valueType === "number" ? "0" : "")
                    : patch.value ?? condition.value
                );

          return {
            ...condition,
            ...patch,
            field: nextField,
            operator: nextOperator,
            value: nextValue
          };
        })
      }
    }));
  }

  function addCondition(listKey: ConditionListKey) {
    updateDraft((current) => ({
      ...current,
      config: {
        ...current.config,
        [listKey]: [...current.config[listKey], createCondition(listKey === "trigger_conditions" ? "ticket_status" : "customer_total_spent")]
      }
    }));
  }

  function removeCondition(listKey: ConditionListKey, conditionId: string) {
    updateDraft((current) => ({
      ...current,
      config: {
        ...current.config,
        [listKey]: current.config[listKey].filter((condition) => condition.id !== conditionId)
      }
    }));
  }

  function addTagToRule(listKey: TagListKey, tagId: number) {
    updateDraft((current) => ({
      ...current,
      config: {
        ...current.config,
        [listKey]: normalizeTagIds([...current.config[listKey], tagId])
      }
    }));
  }

  function removeTagFromRule(listKey: TagListKey, tagId: number) {
    updateDraft((current) => ({
      ...current,
      config: {
        ...current.config,
        [listKey]: current.config[listKey].filter((value) => Number(value) !== Number(tagId))
      }
    }));
  }

  async function handleSaveRule() {
    if (!draft) {
      return;
    }

    const wasNewRule = newRuleId === draft.id;

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      await updateWorkflowRule(draft.id, {
        builder_mode: draft.config.mode,
        config: draft.config as unknown as Record<string, unknown>,
        description: draft.description,
        false_tag_id: getPrimaryTagId(draft.config.else_tag_ids),
        is_enabled: draft.is_enabled,
        name: draft.name,
        true_tag_id: getPrimaryTagId(draft.config.match_tag_ids)
      });
      await loadWorkspace(draft.id);
      setNewRuleId(null);
      setSuccessMessage(wasNewRule ? "Rule created." : "Rule updated.");
    } catch (saveError) {
      setError(saveError instanceof Error ? saveError.message : "Unable to update the rule.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleDuplicateRule() {
    if (!selectedRule) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      const response = await duplicateWorkflowRule(selectedRule.id);
      await loadWorkspace(response.rule?.id ?? null);
      setNewRuleId(null);
      setSuccessMessage("Rule duplicated.");
    } catch (duplicateError) {
      setError(duplicateError instanceof Error ? duplicateError.message : "Unable to duplicate the rule.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleDeleteRule() {
    if (!selectedRule) {
      return;
    }

    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      await deleteWorkflowRule(selectedRule.id);
      await loadWorkspace();
      setNewRuleId(null);
      setSuccessMessage("Rule deleted.");
    } catch (deleteError) {
      setError(deleteError instanceof Error ? deleteError.message : "Unable to delete the rule.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleAddRule() {
    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      const response = await createWorkflowRule();
      const createdRuleId = response.rule?.id ?? null;

      if (!createdRuleId) {
        throw new Error("Unable to create a new rule.");
      }

      await loadWorkspace(createdRuleId);
      setNewRuleId(createdRuleId);
      setDraft(buildFreshRuleDraft(createdRuleId));
      setActiveTab("settings");
      setSuccessMessage("New rule created.");
    } catch (createError) {
      if (isMethodNotAllowedError(createError) && selectedRule) {
        try {
          const duplicateResponse = await duplicateWorkflowRule(selectedRule.id);
          const duplicatedRuleId = duplicateResponse.rule?.id ?? null;

          if (!duplicatedRuleId) {
            throw new Error("Unable to create a new rule.");
          }

          const fallbackConfig = buildCustomRuleConfig([], []);
          await updateWorkflowRule(duplicatedRuleId, {
            builder_mode: "custom",
            config: fallbackConfig as unknown as Record<string, unknown>,
            description: "Create a custom automation rule with Gorgias-style conditions and light tag actions.",
            false_tag_id: null,
            is_enabled: false,
            name: "[Auto Tag] New custom rule",
            true_tag_id: null
          });
          await loadWorkspace(duplicatedRuleId);
          setNewRuleId(duplicatedRuleId);
          setDraft(buildFreshRuleDraft(duplicatedRuleId));
          setActiveTab("settings");
          setSuccessMessage("New rule created.");
          return;
        } catch (fallbackError) {
          setError(fallbackError instanceof Error ? fallbackError.message : "Unable to create a new rule.");
          return;
        }
      }

      setError(createError instanceof Error ? createError.message : "Unable to create a new rule.");
    } finally {
      setIsWorking(false);
    }
  }

  async function handleRestoreDefaultRule() {
    try {
      setIsWorking(true);
      setError("");
      setSuccessMessage("");
      const response = await restoreDefaultWorkflowRule();
      await loadWorkspace(response.rule?.id ?? null);
      setNewRuleId(null);
      setSuccessMessage("Default business-hours rule restored.");
    } catch (restoreError) {
      setError(restoreError instanceof Error ? restoreError.message : "Unable to restore the default rule.");
    } finally {
      setIsWorking(false);
    }
  }

  function handleApplyTemplate() {
    const vipTagIds = tags
      .filter((tag) => ["vip", "during-business-hours"].includes(String(tag.name || "").trim().toLowerCase()))
      .map((tag) => Number(tag.id))
      .filter((tagId) => Number.isFinite(tagId) && tagId > 0);

    updateDraft((current) => ({
      ...current,
      config: buildCustomRuleConfig(vipTagIds, []),
      description: "Tags tickets based on customer spend or order count to identify VIP customers to target",
      is_enabled: true,
      name: "[Auto Tag] Identify VIP customers"
    }));
  }

  function renderConditionRow(condition: WorkflowRuleCondition, listKey: ConditionListKey) {
    const fieldMeta = fieldMetaMap[condition.field] ?? fieldMetaMap.ticket_status;

    return (
      <div className="rules-reference-condition-row" key={condition.id}>
        <select
          className="field-input rules-reference-chip-select"
          onChange={(event) => updateCondition(listKey, condition.id, { field: event.target.value })}
          value={condition.field}
        >
          {Object.entries(fieldMetaMap).map(([fieldKey, meta]) => (
            <option key={fieldKey} value={fieldKey}>
              {meta.label}
            </option>
          ))}
        </select>

        <select
          className="field-input rules-reference-chip-select rules-reference-chip-operator"
          onChange={(event) => updateCondition(listKey, condition.id, { operator: event.target.value })}
          value={condition.operator}
        >
          {fieldMeta.operators.map((operator) => (
            <option key={operator} value={operator}>
              {getOperatorLabel(operator)}
            </option>
          ))}
        </select>

        {fieldMeta.valueType === "none" ? (
          <div className="rules-reference-empty-value">No value needed</div>
        ) : fieldMeta.valueType === "select" ? (
          <select
            className="field-input rules-reference-chip-select rules-reference-chip-value"
            onChange={(event) => updateCondition(listKey, condition.id, { value: event.target.value })}
            value={condition.value}
          >
            {(fieldMeta.values ?? []).map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        ) : (
          <input
            className="field-input rules-reference-chip-input"
            onChange={(event) => updateCondition(listKey, condition.id, { value: event.target.value })}
            placeholder={fieldMeta.valueType === "number" ? "1000" : "Enter value"}
            type={fieldMeta.valueType === "number" ? "number" : "text"}
            value={condition.value}
          />
        )}

        <button
          className="rules-reference-remove-button"
          onClick={() => removeCondition(listKey, condition.id)}
          type="button"
        >
          ×
        </button>
      </div>
    );
  }

  function renderTagActionRow(
    listKey: TagListKey,
    stepLabel: "THEN" | "ELSE",
    stepClassName: "success" | "else"
  ) {
    if (!draft) {
      return null;
    }

    const selectedTagIds = draft.config[listKey];
    const selectedTags = getTagNames(tags, selectedTagIds);
    const availableTags = tags.filter(
      (tag) => !selectedTagIds.includes(Number(tag.id))
    );

    return (
      <div className="rules-reference-action-row">
        <span className={`rules-builder-step-pill ${stepClassName}`}>{stepLabel}</span>

        {selectedTags.length ? (
          selectedTags.map((tag) => (
            <button
              className="rules-reference-tag-chip"
              key={`${listKey}-${tag.id}`}
              onClick={() => removeTagFromRule(listKey, tag.id)}
              type="button"
            >
              {tag.name}
              <span>×</span>
            </button>
          ))
        ) : (
          <span className="rules-reference-empty-inline">No tags added</span>
        )}

        <select
          className="field-input rules-reference-tag-select"
          onChange={(event) => {
            const nextTagId = Number(event.target.value);

            if (nextTagId) {
              addTagToRule(listKey, nextTagId);
              event.target.value = "";
            }
          }}
          value=""
        >
          <option value="">Add tags...</option>
          {availableTags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>
      </div>
    );
  }

  function renderRuleActionRow(
    listKey: TagListKey,
    stepLabel: "THEN" | "ELSE",
    stepClassName: "success" | "else",
    showValidation = false
  ) {
    if (!draft) {
      return null;
    }

    const selectedTagIds = draft.config[listKey];
    const selectedTags = getTagNames(tags, selectedTagIds);
    const availableTags = tags.filter((tag) => !selectedTagIds.includes(Number(tag.id)));

    return (
      <div className="rules-reference-action-row">
        <span className={`rules-builder-step-pill ${stepClassName}`}>{stepLabel}</span>
        {selectedTags.length ? <span className="rules-reference-action-pill">Tags to add</span> : null}

        {selectedTags.map((tag) => (
          <button
            className="rules-reference-tag-chip"
            key={`${listKey}-${tag.id}`}
            onClick={() => removeTagFromRule(listKey, tag.id)}
            type="button"
          >
            {tag.name}
            <span>x</span>
          </button>
        ))}

        <select
          className={`field-input rules-reference-tag-select${showValidation ? " validation" : ""}`}
          onChange={(event) => {
            const nextTagId = Number(event.target.value);

            if (nextTagId) {
              addTagToRule(listKey, nextTagId);
              event.target.value = "";
            }
          }}
          value=""
        >
          <option value="">{showValidation ? "Choose at least one tag" : "Choose a tag to add"}</option>
          {availableTags.map((tag) => (
            <option key={tag.id} value={tag.id}>
              {tag.name}
            </option>
          ))}
        </select>

        {showValidation ? <span className="rules-reference-inline-error">Pick at least one tag for the main action.</span> : null}
      </div>
    );
  }

  return (
    <div className="stack-page rules-screen-page">
      {error ? <div className="banner-error">{error}</div> : null}
      {successMessage ? <div className="banner-success">{successMessage}</div> : null}

      <section className="plain-card rules-screen-shell">
        {isBootstrapping ? (
          <div className="empty-card">Loading rules...</div>
        ) : !rules.length ? (
          <div className="rules-empty-shell">
            <div className="empty-card">No rules yet. Create one simple rule to get started.</div>
            <div className="action-row wrap">
              <button
                className="primary-button"
                disabled={isWorking}
                onClick={() => void handleAddRule()}
                type="button"
              >
                New rule
              </button>
              <button
                className="ghost-button"
                disabled={isWorking}
                onClick={() => void handleRestoreDefaultRule()}
                type="button"
              >
                Bring back default rule
              </button>
            </div>
          </div>
        ) : (
          <div className="rules-editor-panel">
            {selectedRule && draft ? (
              <>
                <div className="rules-simple-hero">
                  <div className="rules-simple-hero-copy">
                    <div className="rules-simple-kicker">Easy Mode</div>
                    <h2>Make AI safe</h2>
                    <p>
                      If a ticket looks like this, do this. Keep it simple.
                    </p>
                  </div>

                  <div className="rules-simple-hero-side">
                    <div className="rules-simple-hero-visual">
                      <img
                        alt="Support operations team coordinating safe routing and escalation decisions"
                        className="rules-simple-hero-image"
                        src="/images/real-world/workspace-ops.png"
                      />
                      <div className="rules-simple-hero-note">
                        <strong>Practical rules for real support moments</strong>
                        <span>Keep routing, approvals, and escalation logic easy for the team to trust.</span>
                      </div>
                    </div>

                    <div className="rules-simple-stat-grid">
                      <div className="rules-simple-stat-card">
                        <span>Rules</span>
                        <strong>{rules.length}</strong>
                      </div>
                      <div className="rules-simple-stat-card">
                        <span>Turned on</span>
                        <strong>{enabledRuleCount}</strong>
                      </div>
                      <div className="rules-simple-stat-card">
                        <span>Checks here</span>
                        <strong>{activeCheckCount}</strong>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="rules-screen-head">
                  <div className="rules-screen-head-main rules-simple-head-main">
                    <div className="rules-simple-head-copy">
                      <div className="rules-simple-kicker">This rule</div>
                      <h3>{draft.name || "New rule"}</h3>
                      <p>{draft.is_enabled ? "This rule is live right now." : "This rule is off until you turn it on."}</p>
                    </div>
                  </div>

                  <div className="rules-screen-toolbar">
                    <label className="field-block rules-screen-rule-picker">
                      <span>Pick a rule</span>
                      <select
                        className="field-input"
                        onChange={(event) => {
                          setSelectedRuleId(Number(event.target.value));
                          setActiveTab("settings");
                          setNewRuleId(null);
                          setSuccessMessage("");
                        }}
                        value={selectedRuleId ?? ""}
                      >
                        {rules.map((rule) => (
                          <option key={rule.id} value={rule.id}>
                            {rule.name}
                          </option>
                        ))}
                      </select>
                    </label>

                    <button
                      className="primary-button"
                      disabled={isWorking}
                      onClick={() => void handleAddRule()}
                      type="button"
                    >
                      New rule
                    </button>
                    <button
                      className="ghost-button"
                      disabled={isWorking}
                      onClick={() => void handleRestoreDefaultRule()}
                      type="button"
                    >
                      Bring back default
                    </button>
                  </div>
                </div>

                <div className="rules-tab-row">
                  <button
                    className={`rules-tab-button${activeTab === "settings" ? " active" : ""}`}
                    onClick={() => setActiveTab("settings")}
                    type="button"
                  >
                    Build rule
                  </button>
                  <button
                    className={`rules-tab-button${activeTab === "affected" ? " active" : ""}`}
                    onClick={() => setActiveTab("affected")}
                    type="button"
                  >
                    See tickets
                  </button>
                </div>

                {activeTab === "settings" ? (
                  <div className={`rules-screen-settings${isNewRule ? " is-new" : ""}`}>
                    <div className="rules-screen-main">
                      <section className="rules-simple-preview-card">
                        <div className="rules-simple-preview-head">
                          <div>
                            <div className="rules-simple-kicker">What this does</div>
                            <h3>{draft.name || "New rule"}</h3>
                          </div>
                          <span className={`rules-simple-status-pill${draft.is_enabled ? " on" : ""}`}>
                            {draft.is_enabled ? "On" : "Off"}
                          </span>
                        </div>
                        <p>{rulePreview}</p>
                        <div className="rules-simple-pill-row">
                          <span className="rules-simple-pill">Type: {draft.config.mode === "business_hours" ? "Business hours" : "Custom"}</span>
                          <span className="rules-simple-pill">Main tags: {matchTags.length}</span>
                          <span className="rules-simple-pill">Else tags: {elseTags.length}</span>
                        </div>
                      </section>

                      <section className="rules-simple-block">
                        <div className="rules-simple-block-head">
                          <div className="rules-simple-step">1</div>
                          <div>
                            <h3>Give this rule a name</h3>
                            <p>Use a short name your team can understand fast.</p>
                          </div>
                        </div>

                        <div className="rules-simple-choice-row">
                          <label className="field-block">
                            <span>Rule name *</span>
                            <input
                              className="field-input"
                              onChange={(event) =>
                                updateDraft((current) => ({
                                  ...current,
                                  name: event.target.value
                                }))
                              }
                              placeholder="Example: VIP customer tag"
                              value={draft.name}
                            />
                          </label>

                          <label className="field-block">
                            <span>Short note</span>
                            <textarea
                              className="field-textarea short"
                              onChange={(event) =>
                                updateDraft((current) => ({
                                  ...current,
                                  description: event.target.value
                                }))
                              }
                              placeholder="What this rule is for"
                              rows={2}
                              value={draft.description}
                            />
                          </label>
                        </div>
                      </section>

                      <section className="rules-simple-block">
                        <div className="rules-simple-block-head">
                          <div className="rules-simple-step">2</div>
                          <div>
                            <h3>When should we look?</h3>
                            <p>Pick the ticket moment that should wake this rule up.</p>
                          </div>
                        </div>

                        <div className="rules-simple-choice-row">
                          <label className="field-block">
                            <span>Run this rule when</span>
                            <select
                              className="field-input"
                              onChange={(event) =>
                                updateDraft((current) => ({
                                  ...current,
                                  config: {
                                    ...current.config,
                                    event: event.target.value
                                  }
                                }))
                              }
                              value={draft.config.event}
                            >
                              {eventOptions.map((option) => (
                                <option key={option.value} value={option.value}>
                                  {option.label}
                                </option>
                              ))}
                            </select>
                          </label>

                          <div className="rules-simple-mode-card">
                            <span>Rule type</span>
                            <strong>{draft.config.mode === "business_hours" ? "Business hours rule" : "Custom matching rule"}</strong>
                            <p>
                              {draft.config.mode === "business_hours"
                                ? "This rule uses business hours logic automatically."
                                : "This rule uses your custom checks below."}
                            </p>
                          </div>
                        </div>
                      </section>

                      <section className="rules-simple-block">
                        <div className="rules-simple-block-head">
                          <div className="rules-simple-step">3</div>
                          <div>
                            <h3>What should we check?</h3>
                            <p>Tell the system what must be true.</p>
                          </div>
                        </div>

                        <section className="rules-reference-condition-card rules-screen-condition-card rules-simple-logic-card">
                          <div className="rules-reference-section-title">Rule flow</div>

                          <div className="rules-reference-flow">
                            <div className="rules-reference-event-row">
                              <span className="rules-builder-step-pill when">START</span>
                              <span className="rules-simple-inline-copy">Whenever {getEventSentence(draft.config.event)}</span>
                            </div>

                            {draft.config.trigger_conditions.length ? (
                              <div className="rules-reference-branch-shell">
                                <div className="rules-reference-step-marker nested">
                                  <span className="rules-builder-step-pill if">CHECK</span>
                                </div>

                                <div className="rules-reference-condition-stack">
                                  {draft.config.trigger_conditions.map((condition) =>
                                    renderConditionRow(condition, "trigger_conditions")
                                  )}
                                </div>
                              </div>
                            ) : (
                              <div className="rules-simple-empty">No checks yet. Add one simple check to get started.</div>
                            )}

                            {draft.config.mode === "custom" && draft.config.branch_conditions.length ? (
                              <div className="rules-reference-branch-shell">
                                <div className="rules-reference-step-marker nested">
                                  <span className="rules-builder-step-pill then">MATCH</span>
                                </div>

                                <div className="rules-reference-step-marker deep">
                                  <span className="rules-builder-step-pill if">EXTRA</span>
                                </div>

                                <div className="rules-reference-condition-stack deep">
                                  {draft.config.branch_conditions.map((condition) =>
                                    renderConditionRow(condition, "branch_conditions")
                                  )}
                                </div>
                              </div>
                            ) : null}

                            {renderRuleActionRow("match_tag_ids", "THEN", "success", !draft.config.match_tag_ids.length)}

                            {(draft.config.mode === "business_hours" ||
                              draft.config.branch_conditions.length > 0 ||
                              draft.config.else_tag_ids.length > 0 ||
                              !isNewRule) &&
                              renderRuleActionRow("else_tag_ids", "ELSE", "else")}

                            <div className="rules-screen-condition-actions">
                              <button
                                className="ghost-button small rules-builder-add"
                                onClick={() => addCondition("trigger_conditions")}
                                type="button"
                              >
                                Add main check
                              </button>

                              {draft.config.mode === "custom" ? (
                                <button
                                  className="ghost-button small rules-builder-add"
                                  onClick={() => addCondition("branch_conditions")}
                                  type="button"
                                >
                                  Add extra match check
                                </button>
                              ) : null}
                            </div>
                          </div>
                        </section>
                      </section>

                      <div className="rules-reference-enable-row rules-simple-toggle-band">
                        <button
                          aria-pressed={draft.is_enabled}
                          className={`rules-toggle-switch${draft.is_enabled ? " on" : ""}`}
                          onClick={() =>
                            updateDraft((current) => ({
                              ...current,
                              is_enabled: !current.is_enabled
                            }))
                          }
                          type="button"
                        >
                          <span />
                        </button>
                        <strong>Use this rule</strong>
                      </div>

                      <div className="rules-reference-footer">
                        <div className="rules-reference-footer-group">
                          <button
                            className="primary-button"
                            disabled={isWorking || !canSaveRule}
                            onClick={() => void handleSaveRule()}
                            type="button"
                          >
                            {isNewRule ? "Save this rule" : "Save changes"}
                          </button>

                          {!isNewRule ? (
                            <button
                              className="ghost-button"
                              disabled={isWorking}
                              onClick={() => void handleDuplicateRule()}
                              type="button"
                            >
                              Copy rule
                            </button>
                          ) : null}
                        </div>

                        {!isNewRule ? (
                          <button
                            className="mini-danger"
                            disabled={isWorking}
                            onClick={() => void handleDeleteRule()}
                            type="button"
                          >
                            Delete
                          </button>
                        ) : null}
                      </div>
                    </div>

                    {isNewRule ? (
                      <aside className="rules-screen-inspiration-card">
                        <h3>Quick start</h3>
                        <p>Use one ready example, then change the name and tags to fit your team.</p>
                        <button
                          className="dark-button"
                          onClick={handleApplyTemplate}
                          type="button"
                        >
                          Use VIP example
                        </button>
                      </aside>
                    ) : null}
                  </div>
                ) : (
                  <div className="rules-affected-shell">
                    <section className="rules-simple-preview-card">
                      <div className="rules-simple-preview-head">
                        <div>
                          <div className="rules-simple-kicker">Ticket preview</div>
                          <h3>See where this rule shows up</h3>
                        </div>
                        <span className={`rules-simple-status-pill${draft.is_enabled ? " on" : ""}`}>
                          {draft.is_enabled ? "Live" : "Off"}
                        </span>
                      </div>
                      <p>Use this tab to check the tickets touched by the current rule.</p>

                      <div className="rules-affected-summary">
                        <div className="rules-summary-card">
                          <span>Total</span>
                          <strong>{affectedSummary.total}</strong>
                        </div>
                        <div className="rules-summary-card">
                          <span>During hours</span>
                          <strong>{affectedSummary.during}</strong>
                        </div>
                        <div className="rules-summary-card">
                          <span>Outside hours</span>
                          <strong>{affectedSummary.outside}</strong>
                        </div>
                      </div>
                    </section>

                    {isLoadingAffected ? (
                      <div className="empty-card">Loading tickets...</div>
                    ) : affectedTickets.length ? (
                      <div className="rules-ticket-grid">
                        {affectedTickets.map((ticket) => (
                          <article className="rules-ticket-card" key={ticket.ticket_id}>
                            <div className="rules-ticket-card-top">
                              <strong>{ticket.ticket_id}</strong>
                              <span className="schedule-pill">{ticket.priority}</span>
                            </div>
                            <div className="rules-ticket-card-copy">{ticket.customer_email}</div>
                            <div className="rules-ticket-card-copy">{ticket.issue}</div>
                            <div className="rules-ticket-tag-row">
                              <span className="rules-ticket-soft-chip">{ticket.status}</span>
                              <span className="rules-ticket-soft-chip">{ticket.business_hours_tag}</span>
                              <span className="rules-ticket-soft-chip">{ticket.applied_tag || "No rule tag applied"}</span>
                            </div>
                          </article>
                        ))}
                      </div>
                    ) : (
                      <div className="empty-card">No tickets are linked to this rule yet.</div>
                    )}
                  </div>
                )}
              </>
            ) : (
              <div className="empty-card tall">Pick a rule to build it or see its tickets.</div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
