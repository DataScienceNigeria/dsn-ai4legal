"use client";

import * as React from "react";

import { useRoles, useSession } from "@/components/app/session";
import {
  Button,
  Card,
  CardBody,
  CardHeader,
  DataState,
  Empty,
  Field,
  Input,
  Modal,
  Mono,
  Notice,
  PageTitle,
  Pill,
  Refusal,
  Row,
  Select,
  Tabs,
  Textarea,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useAction, useApi } from "@/lib/hooks";
import type { CounterpartyRow, VendorRow } from "@/lib/types";
import { formatDate, titleCase } from "@/lib/utils";

const PARTY_COLS = "7.5rem minmax(0,1.4fr) 8.125rem 9.375rem 8.125rem 6.25rem 10.625rem";

const COUNTERPARTY_TYPES = ["company", "individual", "government", "ngo", "academic"];
const RELATIONSHIP_CLASSES = ["commercial", "strategic", "regulator", "funder", "vendor", "partner"];
const VENDOR_COLS = "minmax(0,1.3fr) 9.375rem 8.125rem 8.125rem 7.5rem minmax(0,1fr)";

type RenewalRisk = {
  vendor_id: string;
  counterparty: string | null;
  renewal_date: string | null;
  clear_to_renew: boolean;
  blockers: string[];
};

type Duplicate = { id: string; reference: string; legal_name: string; similarity: number };

type CreateResult = { created: CounterpartyRow | null; duplicates: Duplicate[]; message: string };

type PositionHistory = {
  clause_category: string;
  house_position: string;
  unacceptable_position: string | null;
  deviations: {
    matter_number: string | null;
    counterparty: string | null;
    position_taken: string;
    outcome: string | null;
    authority: string | null;
    decided_at: string | null;
  }[];
};

type HistoryPayload = {
  matters?: { number: string; title: string; status: string }[];
  contracts?: { reference: string; agreement_type: string; executed_at: string | null }[];
  concessions?: {
    sequence: number;
    decision: string;
    reason: string | null;
    authority_level: string | null;
    decided_at: string | null;
  }[];
  negotiation_notes?: string | null;
};

function History({ id }: Readonly<{ id: string }>) {
  const history = useApi<HistoryPayload>(`/counterparties/${id}/history`, [id]);
  const data = history.data ?? {};
  const matters = data.matters ?? [];
  const concessions = data.concessions ?? [];

  return (
    <DataState
      loading={history.loading}
      errorMessage={history.error?.message}
      errorTitle="That history is not available to you"
      isEmpty={false}
    >
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader title="Matters" />
          <CardBody>
            {matters.length === 0 ? (
              <Empty title="No matter has been opened against this counterparty" />
            ) : (
              <ul className="space-y-2">
                {matters.map((matter) => (
                  <li key={matter.number} className="text-sm">
                    <Mono>{matter.number}</Mono>
                    <div className="truncate">{matter.title}</div>
                    <Pill tone="neutral">{titleCase(matter.status)}</Pill>
                  </li>
                ))}
              </ul>
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title="Positions taken and concessions granted" />
          <CardBody>
            {concessions.length === 0 ? (
              <Empty title="No position has been recorded against this counterparty" />
            ) : (
              <ul className="space-y-2">
                {concessions.map((concession) => (
                  <li key={concession.sequence} className="text-sm">
                    <span className="font-medium">{concession.decision}</span>
                    {concession.reason ? (
                      <div className="text-muted-foreground">{concession.reason}</div>
                    ) : null}
                    <div className="text-xs text-muted-foreground">
                      {`Authority: ${titleCase(concession.authority_level ?? "not recorded")}`}
                      {concession.decided_at ? ` on ${formatDate(concession.decided_at)}` : ""}
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {data.negotiation_notes ? (
              <p className="mt-3 text-xs text-muted-foreground">{data.negotiation_notes}</p>
            ) : null}
          </CardBody>
        </Card>
      </div>
    </DataState>
  );
}

/*
  One counterparty, one permanent identity. Creation warns on likely duplicates
  and offers a merge instead, because two records for the same company is how
  a negotiation history quietly stops being one.
*/
function CreateCounterparty({ onDone }: Readonly<{ onDone: () => void }>) {
  const [open, setOpen] = React.useState(false);
  const [legalName, setLegalName] = React.useState("");
  const [type, setType] = React.useState("company");
  const [registration, setRegistration] = React.useState("");
  const [domain, setDomain] = React.useState("");
  const [jurisdiction, setJurisdiction] = React.useState("Nigeria");
  const [relationship, setRelationship] = React.useState("commercial");
  const [duplicates, setDuplicates] = React.useState<Duplicate[]>([]);
  const [confirm, setConfirm] = React.useState(false);

  const create = useAction(async () => {
    const result = await api<CreateResult>("/counterparties", {
      method: "POST",
      body: {
        legal_name: legalName,
        counterparty_type: type,
        registration_number: registration || undefined,
        domain: domain || undefined,
        jurisdiction,
        relationship_class: relationship,
        confirm_despite_duplicates: confirm,
      },
    });
    if (result.created) {
      onDone();
      setOpen(false);
      setLegalName("");
      setDuplicates([]);
      setConfirm(false);
      return;
    }
    setDuplicates(result.duplicates);
  });

  return (
    <>
      <Button variant="primary" onClick={() => setOpen(true)}>
        Add a counterparty
      </Button>
      <Modal
        open={open}
        title="Add a counterparty"
        subtitle="The identifier is permanent. A later name change updates the record and keeps it."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={legalName.trim().length < 2 || create.busy}
              onClick={() => void create.run()}
            >
              {duplicates.length && confirm ? "Create it anyway" : "Create"}
            </Button>
          </>
        }
      >
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Legal name" required>
            <Input value={legalName} onChange={(event) => setLegalName(event.target.value)} />
          </Field>
          <Field label="Type">
            <Select value={type} onChange={(event) => setType(event.target.value)}>
              {COUNTERPARTY_TYPES.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Registration number">
            <Input value={registration} onChange={(event) => setRegistration(event.target.value)} />
          </Field>
          <Field label="Domain">
            <Input value={domain} onChange={(event) => setDomain(event.target.value)} />
          </Field>
          <Field label="Jurisdiction">
            <Input value={jurisdiction} onChange={(event) => setJurisdiction(event.target.value)} />
          </Field>
          <Field label="Relationship">
            <Select value={relationship} onChange={(event) => setRelationship(event.target.value)}>
              {RELATIONSHIP_CLASSES.map((value) => (
                <option key={value} value={value}>
                  {titleCase(value)}
                </option>
              ))}
            </Select>
          </Field>
        </div>

        {duplicates.length ? (
          <Notice tone="warn" title={`${duplicates.length} existing records look like this one`}>
            <ul className="mt-1 space-y-1">
              {duplicates.map((duplicate) => (
                <li key={duplicate.id}>
                  {duplicate.legal_name}, {duplicate.reference},{" "}
                  {Math.round(duplicate.similarity * 100)}% alike
                </li>
              ))}
            </ul>
            <label className="mt-2 flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={confirm}
                onChange={(event) => setConfirm(event.target.checked)}
              />{" "}
              This is a separate legal entity
            </label>
          </Notice>
        ) : null}

        {create.error ? (
          <Refusal title="That counterparty was not created" reason={create.error.message} />
        ) : null}
      </Modal>
    </>
  );
}

/*
  There was no way to change a counterparty at all. An address an agreement
  names could only be typed into each document, and a registration number
  learned during diligence had nowhere to live, so the same facts were retyped
  every time and disagreed with each other in the archive.
*/
function EditCounterparty({
  row,
  onDone,
}: Readonly<{ row: CounterpartyRow; onDone: () => void }>) {
  const { has } = useRoles();
  const [open, setOpen] = React.useState(false);
  const [draft, setDraft] = React.useState<Record<string, string>>({});

  const save = useAction(async () => {
    await api(`/counterparties/${row.id}`, { method: "PATCH", body: draft });
    setDraft({});
    onDone();
    setOpen(false);
  });

  if (!has("counsel", "head_of_legal", "admin")) return null;

  const value = (name: keyof CounterpartyRow) =>
    draft[name] ?? ((row[name] as string | null) ?? "");

  const set = (name: string) => (event: { target: { value: string } }) =>
    setDraft((previous) => ({ ...previous, [name]: event.target.value }));

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Edit
      </Button>
      <Modal
        open={open}
        title={row.legal_name}
        subtitle="What an agreement names this party by. Changes are audited with both states, because these are copied into contracts that may already be signed."
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={Object.keys(draft).length === 0 || save.busy}
              onClick={() => void save.run()}
            >
              {save.busy ? "Saving" : "Save the record"}
            </Button>
          </>
        }
      >
        <Field label="Legal name" required hint="Exactly as registered.">
          <Input value={value("legal_name")} onChange={set("legal_name")} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Registration number">
            <Input value={value("registration_number")} onChange={set("registration_number")} />
          </Field>
          <Field label="Jurisdiction">
            <Input value={value("jurisdiction")} onChange={set("jurisdiction")} />
          </Field>
        </div>
        <Field
          label="Registered address"
          hint="One line, as it should read in a preamble. Generation fills the counterparty address from this."
        >
          <Input value={value("registered_address")} onChange={set("registered_address")} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Domain">
            <Input value={value("domain")} onChange={set("domain")} />
          </Field>
          <Field label="Relationship">
            <Input value={value("relationship_class")} onChange={set("relationship_class")} />
          </Field>
        </div>
        <Field label="Negotiation notes" hint="Read by anyone drafting against this party.">
          <Textarea value={value("negotiation_notes")} onChange={set("negotiation_notes")} />
        </Field>
        {save.error ? (
          <Refusal
            title="That change was refused"
            reason={save.error.message}
            reasons={Object.values(save.error.fieldErrors ?? {})}
          />
        ) : null}
      </Modal>
    </>
  );
}

function MergeCounterparty({
  row,
  others,
  onDone,
}: Readonly<{ row: CounterpartyRow; others: CounterpartyRow[]; onDone: () => void }>) {
  const { has } = useRoles();
  const [open, setOpen] = React.useState(false);
  const [into, setInto] = React.useState("");
  const [reason, setReason] = React.useState("");

  const merge = useAction(async () => {
    await api(`/counterparties/${row.id}/merge`, {
      method: "POST",
      body: { into_id: into, reason },
    });
    onDone();
    setOpen(false);
  });

  if (!has("counsel", "head_of_legal", "admin")) return null;

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Merge
      </Button>
      <Modal
        open={open}
        title={`Merge ${row.legal_name}`}
        subtitle="The surviving record keeps its identifier and inherits the matters, contracts and positions of the one being merged."
        width="sm"
        onClose={() => setOpen(false)}
        footer={
          <>
            <Button onClick={() => setOpen(false)}>Cancel</Button>
            <Button
              variant="primary"
              disabled={!into || reason.trim().length < 5 || merge.busy}
              onClick={() => void merge.run()}
            >
              Merge them
            </Button>
          </>
        }
      >
        <Field label="Merge into" required>
          <Select value={into} onChange={(event) => setInto(event.target.value)}>
            <option value="">Choose the surviving record</option>
            {others.map((other) => (
              <option key={other.id} value={other.id}>
                {other.legal_name}, {other.reference}
              </option>
            ))}
          </Select>
        </Field>
        <Field label="Reason" required>
          <Textarea value={reason} onChange={(event) => setReason(event.target.value)} />
        </Field>
        {merge.error ? <Refusal title="That merge was refused" reason={merge.error.message} /> : null}
      </Modal>
    </>
  );
}

function Positions() {
  const clauses = useApi<{ category: string; name: string }[]>("/clauses");
  const [category, setCategory] = React.useState("");
  const history = useApi<PositionHistory>(category ? `/ai/positions/${category}` : null, [category]);

  return (
    <div className="space-y-4">
      <Notice tone="info" title="What we have actually agreed before">
        The house position is what we ask for. This is what we settled on, matter by matter, and
        the authority under which each concession was granted.
      </Notice>

      <Card>
        <CardHeader
          title="Position history by clause"
          actions={
            <Select value={category} onChange={(event) => setCategory(event.target.value)}>
              <option value="">Choose a clause category</option>
              {(clauses.data ?? []).map((clause) => (
                <option key={clause.category} value={clause.category}>
                  {clause.name}
                </option>
              ))}
            </Select>
          }
        />
        <CardBody>
          {category ? (
            <DataState
              loading={history.loading}
              errorMessage={history.error?.message}
              isEmpty={(history.data?.deviations ?? []).length === 0}
              emptyTitle="No deviation from the house position has been recorded on this clause"
            >
              <div className="space-y-3">
                <div className="rounded-md border border-brand/20 bg-brand/5 p-3 text-sm leading-relaxed">
                  {history.data?.house_position}
                </div>
                {(history.data?.deviations ?? []).map((deviation, index) => (
                  <div
                    key={`${deviation.matter_number ?? "unlinked"}-${index}`}
                    className="rounded-md border p-3"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <Mono>{deviation.matter_number ?? "Not linked"}</Mono>
                      <span className="text-sm font-medium">{deviation.counterparty ?? "Unnamed"}</span>
                      <Pill tone="info">{titleCase(deviation.authority ?? "not recorded")}</Pill>
                      <span className="ml-auto text-xs text-muted-foreground">
                        {formatDate(deviation.decided_at)}
                      </span>
                    </div>
                    <p className="mt-1.5 text-sm leading-relaxed">{deviation.position_taken}</p>
                    {deviation.outcome ? (
                      <p className="mt-1 text-xs text-muted-foreground">{deviation.outcome}</p>
                    ) : null}
                  </div>
                ))}
              </div>
            </DataState>
          ) : (
            <Empty title="Choose a clause category to see what has been conceded" />
          )}
        </CardBody>
      </Card>
    </div>
  );
}

function PartyRow({
  row,
  others,
  expanded,
  onToggle,
  onChanged,
}: Readonly<{
  row: CounterpartyRow;
  others: CounterpartyRow[];
  expanded: boolean;
  onToggle: () => void;
  onChanged: () => void;
}>) {
  return (
    <>
      <Row cols={PARTY_COLS}>
        <div>
          <Mono>{row.reference}</Mono>
        </div>
        <button
          type="button"
          className="min-w-0 truncate text-left text-sm font-medium hover:underline"
          onClick={onToggle}
        >
          {row.legal_name}
          {row.trading_names.length > 0 ? (
            <div className="truncate text-xs text-muted-foreground">
              {`Also known as ${row.trading_names.join(", ")}`}
            </div>
          ) : null}
        </button>
        <div className="text-sm">{titleCase(row.counterparty_type)}</div>
        <div className="text-sm">{row.registration_number ?? "Not recorded"}</div>
        <div className="text-sm">{titleCase(row.relationship_class)}</div>
        <div>
          <Pill tone={row.risk_class === "standard" ? "neutral" : "warn"}>
            {titleCase(row.risk_class)}
          </Pill>
        </div>
        <div className="flex items-center gap-1.5">
          <EditCounterparty row={row} onDone={onChanged} />
          <MergeCounterparty row={row} others={others} onDone={onChanged} />
        </div>
      </Row>
      {expanded ? (
        <div className="border-b bg-muted/30 p-4">
          <History id={row.id} />
        </div>
      ) : null}
    </>
  );
}

function Parties({ entity }: Readonly<{ entity: string }>) {
  const counterparties = useApi<CounterpartyRow[]>("/counterparties", [entity]);
  const [query, setQuery] = React.useState("");
  const [open, setOpen] = React.useState<string | null>(null);

  const rows = (counterparties.data ?? []).filter((row) =>
    query ? row.legal_name.toLowerCase().includes(query.toLowerCase()) : true,
  );

  return (
    <Card>
      <CardHeader
        title="Counterparties"
        subtitle="A name change updates the record and keeps the identifier."
        actions={
          <>
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search by legal name"
            />
            <CreateCounterparty onDone={() => counterparties.reload()} />
          </>
        }
      />
      <div className="table-scroll">
        <div className="min-w-[60rem]">
          <Row cols={PARTY_COLS} head>
            <div>Identifier</div>
            <div>Legal name</div>
            <div>Type</div>
            <div>Registration</div>
            <div>Relationship</div>
            <div>Risk</div>
            <div>Actions</div>
          </Row>
          <DataState
            loading={counterparties.loading}
            errorMessage={counterparties.error?.message}
            errorTitle="Counterparties are not available to you"
            isEmpty={rows.length === 0}
            emptyTitle="No counterparty matches"
          >
            {rows.map((row) => (
              <PartyRow
                key={row.id}
                row={row}
                others={(counterparties.data ?? []).filter((other) => other.id !== row.id)}
                expanded={open === row.id}
                onToggle={() => setOpen(open === row.id ? null : row.id)}
                onChanged={() => counterparties.reload()}
              />
            ))}
          </DataState>
        </div>
      </div>
    </Card>
  );
}

function RenewalCell({
  vendor,
  outcome,
  busy,
  onCheck,
}: Readonly<{
  vendor: VendorRow;
  outcome: RenewalRisk | undefined;
  busy: boolean;
  onCheck: () => void;
}>) {
  if (!outcome) {
    return (
      <Button size="sm" disabled={busy} onClick={onCheck}>
        Check renewal risk
      </Button>
    );
  }
  return (
    <div className="text-xs">
      <Pill tone={outcome.clear_to_renew ? "good" : "bad"}>
        {outcome.clear_to_renew ? "Clear to renew" : "Do not renew yet"}
      </Pill>
      <ul className="mt-1 space-y-0.5 text-muted-foreground">
        {outcome.blockers.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
    </div>
  );
}

function Vendors({ entity }: Readonly<{ entity: string }>) {
  const vendors = useApi<VendorRow[]>("/vendors", [entity]);
  const [risk, setRisk] = React.useState<Record<string, RenewalRisk>>({});

  const checkRenewal = useAction(async (vendorId: string) => {
    const result = await api<RenewalRisk>(`/vendors/${vendorId}/renewal-risk`);
    setRisk((previous) => ({ ...previous, [vendorId]: result }));
  });

  const rows = vendors.data ?? [];

  return (
    <div className="space-y-4">
      <Notice tone="info" title="Renewal is the moment risk becomes visible">
        The renewal check surfaces outstanding security findings, expired assessments and
        unresolved performance issues before the term rolls over.
      </Notice>

      {checkRenewal.error ? (
        <Refusal title="That check was refused" reason={checkRenewal.error.message} />
      ) : null}

      <Card>
        <CardHeader title="Vendors" />
        <div className="table-scroll">
          <div className="min-w-[56.25rem]">
            <Row cols={VENDOR_COLS} head>
              <div>Vendor</div>
              <div>Security review</div>
              <div>Open findings</div>
              <div>Renewal</div>
              <div>Spend band</div>
              <div>Renewal risk</div>
            </Row>
            <DataState
              loading={vendors.loading}
              errorMessage={vendors.error?.message}
              errorTitle="Vendors are not available to you"
              isEmpty={rows.length === 0}
              emptyTitle="No vendor record exists yet"
            >
              {rows.map((vendor) => (
                <Row key={vendor.id} cols={VENDOR_COLS}>
                  <div className="min-w-0 truncate text-sm font-medium">
                    {vendor.legal_name ?? "Unnamed vendor"}
                  </div>
                  <div className="text-sm">
                    {titleCase(vendor.security_review_status)}
                    {vendor.assessment_expired ? (
                      <div>
                        <Pill tone="bad">Assessment expired</Pill>
                      </div>
                    ) : null}
                  </div>
                  <div>
                    <Pill tone={vendor.open_security_findings > 0 ? "warn" : "neutral"}>
                      {vendor.open_security_findings}
                    </Pill>
                  </div>
                  <div className="text-sm">
                    {vendor.renewal_date ? formatDate(vendor.renewal_date) : "Not set"}
                  </div>
                  <div className="text-sm">{vendor.spend_band ?? "Not banded"}</div>
                  <div>
                    <RenewalCell
                      vendor={vendor}
                      outcome={risk[vendor.id]}
                      busy={checkRenewal.busy}
                      onCheck={() => checkRenewal.run(vendor.id)}
                    />
                  </div>
                </Row>
              ))}
            </DataState>
          </div>
        </div>
      </Card>
    </div>
  );
}

export default function Counterparties() {
  const { entity } = useSession();
  const [tab, setTab] = React.useState("counterparties");

  return (
    <div className="space-y-6">
      <PageTitle
        title="Counterparties and vendors"
        subtitle={
          "One permanent identity per counterparty, and one record per vendor carrying the " +
          "contracts, reviews and renewal risk that belong to it."
        }
      />

      <Tabs
        tabs={[
          { id: "counterparties", label: "Counterparties" },
          { id: "vendors", label: "Vendors" },
          { id: "positions", label: "Positions" },
        ]}
        active={tab}
        onChange={setTab}
      />

      {tab === "counterparties" ? <Parties entity={entity} /> : null}
      {tab === "vendors" ? <Vendors entity={entity} /> : null}
      {tab === "positions" ? <Positions /> : null}
    </div>
  );
}
