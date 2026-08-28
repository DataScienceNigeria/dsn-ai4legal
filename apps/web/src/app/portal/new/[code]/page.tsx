"use client";

import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  Confirm,
  Field,
  Input,
  Notice,
  PageTitle,
  Refusal,
  Select,
  Spinner,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { BriefSection, FieldDefinition, RequestType } from "@/lib/types";
import { cn } from "@/lib/utils";

type Answers = Record<string, string | boolean>;

function inputType(type: string): string {
  if (type === "date") return "date";
  if (type === "number") return "number";
  return "text";
}

/*
  Questions render conditionally, and optional detail sits behind progressive
  disclosure, so no request type shows more than a dozen fields at once.
*/
function visible(field: FieldDefinition, answers: Answers, expanded: boolean): boolean {
  if (field.progressive && !expanded) return false;
  if (!field.condition) return true;
  const value = answers[field.condition];
  return Boolean(value) && value !== "false" && value !== "no";
}

const ENTITY_NAMES: Record<string, string> = {
  DSN: "Data Science Nigeria",
  EAI: "EqualyzAI",
};

export default function NewRequest() {
  const { code } = useParams<{ code: string }>();
  const router = useRouter();
  const { me, entity, setEntity } = useSession();

  const types = useApi<RequestType[]>("/requests/types");
  const sections = useApi<BriefSection[]>("/requests/brief-sections");
  const type = types.data?.find((item) => item.code === code);

  const [raisingFor, setRaisingFor] = React.useState(entity);
  const [answers, setAnswers] = React.useState<Answers>({});
  const [expanded, setExpanded] = React.useState(false);
  const [abandoning, setAbandoning] = React.useState(false);
  const [declaration, setDeclaration] = React.useState({
    personal_data: false,
    special_category_data: false,
    third_party_confidential: false,
    leaves_nigeria: false,
  });

  const submit = useAction(async () => {
    const created = await api<{ id: string; reference: string }>("/requests", {
      method: "POST",
      body: {
        request_type_code: code,
        entity: raisingFor,
        subject: String(answers.subject ?? answers.counterparty ?? type?.business_label ?? ""),
        purpose: String(answers.purpose ?? ""),
        proposed_counterparty: answers.counterparty ? String(answers.counterparty) : null,
        required_date: answers.required_date ? String(answers.required_date) : null,
        value_amount: answers.value_amount ? Number(answers.value_amount) : null,
        ...declaration,
        answers,
      },
    });
    router.push(`/portal/submitted/${created.id}`);
    return created;
  });

  React.useEffect(() => {
    setRaisingFor(entity);
  }, [entity]);

  // Hooks run before any early return, so the field list is read from the
  // request type where there is one and is empty where there is not.
  const fields = React.useMemo(() => type?.fields ?? [], [type]);
  /*
    The brief's groups, in the guide's order, holding only the fields that are
    visible right now. A group with nothing showing is not rendered at all: an
    empty card with a heading reads as a section somebody forgot to fill in.

    Fields a request type asked for before the brief existed carry no group.
    They are what the requester came to answer, so they lead, under the first
    heading.
  */
  const groups = React.useMemo(() => {
    const shown = fields.filter((field) => visible(field, answers, expanded));
    const order = sections.data ?? [];
    const known = new Set(order.map((section) => section.key));
    return order
      .map((section) => ({
        ...section,
        title: `${section.letter}. ${section.title}`,
        fields: shown.filter((field) => {
          const key = field.section && known.has(field.section) ? field.section : "brief";
          return key === section.key;
        }),
      }))
      .filter((group) => group.fields.length > 0);
  }, [fields, answers, expanded, sections.data]);

  if (types.loading) return <Spinner />;
  if (!type) return <Refusal title="That request type is not available" />;

  const anyPrivacy = Object.values(declaration).some(Boolean);
  const entities = me?.entities ?? [];
  const fieldErrors = submit.error?.fieldErrors ?? {};
  const hasProgressive = fields.some((field) => field.progressive);



  return (
    <div className="space-y-6">
      <PageTitle
        title={type.business_label}
        subtitle="You are only asked what this request type requires."
      />

      {submit.error ? (
        <Refusal
          title="This request cannot be submitted yet"
          reason={submit.error.message}
          reasons={Object.values(fieldErrors)}
        />
      ) : null}

      <Card>
        <CardHeader
          title="Which organisation is this for?"
          subtitle="The two are separate legal entities. This decides which paper is used, which approvals apply and who can see the matter afterwards, so it cannot be changed later without raising the request again."
        />
        <CardBody>
          {entities.length > 1 ? (
            <div className="grid gap-2 sm:grid-cols-2">
              {entities.map((code) => (
                <label
                  key={code}
                  htmlFor={`entity-${code}`}
                  className={cn(
                    "grid cursor-pointer grid-cols-[auto_minmax(0,1fr)] items-start gap-x-3 gap-y-0.5 rounded-md border p-3.5 text-sm transition-colors sm:p-4",
                    raisingFor === code
                      ? "border-heading bg-heading/[0.07]"
                      : "hover:bg-foreground/[0.04]",
                  )}
                >
                  <input
                    id={`entity-${code}`}
                    type="radio"
                    name="entity"
                    value={code}
                    checked={raisingFor === code}
                    onChange={() => {
                      setRaisingFor(code);
                      setEntity(code);
                    }}
                    className="row-span-2 mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--brand))]"
                  />
                  <span className="min-w-0 font-medium">{ENTITY_NAMES[code] ?? code}</span>
                  <span className="col-start-2 text-xs text-muted-foreground">{code}</span>
                </label>
              ))}
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {ENTITY_NAMES[raisingFor] ?? raisingFor}. Your account is on one organisation, so
              there is nothing to choose.
            </p>
          )}
        </CardBody>
      </Card>

      {/*
        The Contract Brief, section 3 of the guide, in its own nine groups.

        Twenty-five fields in one column is a form nobody finishes, and the
        guide's own lettering is what the legal team already uses when they ask
        for something missing, so a group carries its letter. Only the groups
        Legal cannot start without are asked plainly; the rest sit behind
        optional detail.
      */}
      {groups.map((group) => (
      <Card key={group.key}>
        <CardHeader
          title={group.title}
          subtitle={group.intent}
        />
        <CardBody className="space-y-4">
          {group.fields.map((field) => (
            <Field
                key={field.name}
                label={field.label}
                required={field.mandatory}
                hint={field.help_text}
                error={fieldErrors[field.name]}
              >
                {field.type === "text" ? (
                  <Textarea
                    value={String(answers[field.name] ?? "")}
                    onChange={(event) =>
                      setAnswers((prev) => ({ ...prev, [field.name]: event.target.value }))
                    }
                  />
                ) : field.type === "boolean" ? (
                  <Select
                    value={String(answers[field.name] ?? "")}
                    onChange={(event) =>
                      setAnswers((prev) => ({ ...prev, [field.name]: event.target.value }))
                    }
                  >
                    <option value="">Not stated</option>
                    <option value="true">Yes</option>
                    <option value="false">No</option>
                  </Select>
                ) : (
                  <div className="flex items-center gap-2">
                    <Input
                      type={inputType(field.type)}
                      value={String(answers[field.name] ?? "")}
                      onChange={(event) =>
                        setAnswers((prev) => ({ ...prev, [field.name]: event.target.value }))
                      }
                      className="flex-1"
                    />
                    {field.unit ? (
                      <span className="shrink-0 text-sm text-muted-foreground">{field.unit}</span>
                    ) : null}
                  </div>
                )}
            </Field>
          ))}
        </CardBody>
      </Card>
      ))}

      {hasProgressive && !expanded ? (
        <Button variant="ghost" size="sm" onClick={() => setExpanded(true)}>
          Add the rest of the brief
        </Button>
      ) : null}

      <Card>
        <CardHeader
          title="What data is involved?"
          subtitle="A yes on any of these sets a privacy flag on the matter and tells the legal team."
        />
        <CardBody className="space-y-2">
          {(
            [
              ["personal_data", "Personal data about identifiable people"],
              ["special_category_data", "Special-category data, for example health or biometric data"],
              ["third_party_confidential", "Confidential information belonging to a third party"],
              ["leaves_nigeria", "Data that will leave Nigeria"],
            ] as const
          ).map(([key, label]) => (
            <label
              key={key}
              className="flex cursor-pointer items-start gap-3 rounded-md border p-3.5 text-sm hover:bg-muted/40 sm:p-4"
            >
              <input
                type="checkbox"
                checked={declaration[key]}
                onChange={(event) =>
                  setDeclaration((prev) => ({ ...prev, [key]: event.target.checked }))
                }
                className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--brand))]"
              />
              <span className="leading-relaxed">{label}</span>
            </label>
          ))}

          {anyPrivacy ? (
            <Notice tone="warn" title="A privacy review will be triggered">
              This does not slow your request down. It routes a parallel review so the answer you
              get is one the organisation can stand behind.
            </Notice>
          ) : null}
        </CardBody>
      </Card>

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
        <Button
          variant="primary"
          disabled={submit.busy}
          onClick={() => void submit.run()}
          className="w-full sm:w-auto"
        >
          {submit.busy ? "Submitting" : "Submit the request"}
        </Button>
        <Button
          disabled={submit.busy}
          onClick={() => setAbandoning(true)}
          className="w-full sm:w-auto"
        >
          Cancel
        </Button>
        <span className="text-sm text-muted-foreground">
          Submitting as {me?.name} for {ENTITY_NAMES[raisingFor] ?? raisingFor}. You will get an
          acknowledgment within a minute.
        </span>
      </div>

      <Confirm
        open={abandoning}
        title="Leave this request?"
        detail="Nothing has been sent to Legal, so there is nothing to withdraw. What you have typed is discarded and you go back to the list of request types."
        confirmLabel="Discard and go back"
        destructive
        onCancel={() => setAbandoning(false)}
        onConfirm={() => router.push("/portal")}
      />
    </div>
  );
}
