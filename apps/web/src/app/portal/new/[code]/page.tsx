"use client";

import { useParams, useRouter } from "next/navigation";
import * as React from "react";

import { useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
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
import type { FieldDefinition, RequestType } from "@/lib/types";

type Answers = Record<string, string | boolean>;

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

export default function NewRequest() {
  const { code } = useParams<{ code: string }>();
  const router = useRouter();
  const { me, entity } = useSession();

  const types = useApi<RequestType[]>("/requests/types");
  const type = types.data?.find((item) => item.code === code);

  const [answers, setAnswers] = React.useState<Answers>({});
  const [expanded, setExpanded] = React.useState(false);
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
        entity,
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

  if (types.loading) return <Spinner />;
  if (!type) return <Refusal title="That request type is not available" />;

  const anyPrivacy = Object.values(declaration).some(Boolean);
  const fieldErrors = submit.error?.fieldErrors ?? {};
  const hasProgressive = type.fields.some((field) => field.progressive);

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
        <CardHeader title="About the request" />
        <CardBody className="space-y-4">
          {type.fields
            .filter((field) => visible(field, answers, expanded))
            .map((field) => (
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
                  <Input
                    type={field.type === "date" ? "date" : field.type === "number" ? "number" : "text"}
                    value={String(answers[field.name] ?? "")}
                    onChange={(event) =>
                      setAnswers((prev) => ({ ...prev, [field.name]: event.target.value }))
                    }
                  />
                )}
              </Field>
            ))}

          {hasProgressive && !expanded ? (
            <Button variant="ghost" size="sm" onClick={() => setExpanded(true)}>
              Add optional detail
            </Button>
          ) : null}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="What data is involved?"
          subtitle="A yes on any of these sets a privacy flag on the matter and notifies the data protection officer."
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
                className="mt-0.5 h-4 w-4 shrink-0 accent-[hsl(var(--primary))]"
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
        <span className="text-sm text-muted-foreground">
          Submitting as {me?.name} in {entity}. You will get an acknowledgment within a minute.
        </span>
      </div>
    </div>
  );
}
