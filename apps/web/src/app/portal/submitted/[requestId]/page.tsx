"use client";

import { useParams, useRouter, useSearchParams } from "next/navigation";

import { Attachments } from "@/components/app/attachments";
import { Button, Card, CardBody, Mono, Notice, PageTitle, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { RequestStatus } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function Submitted() {
  const { requestId } = useParams<{ requestId: string }>();
  const router = useRouter();
  const refused = useSearchParams().get("refused");
  const { data, loading } = useApi<RequestStatus>(`/requests/${requestId}/status`);

  if (loading) return <Spinner />;
  if (!data) return null;

  return (
    <div className="space-y-6">
      <PageTitle
        title="Received. Nothing more is needed from you."
        subtitle="Legal has your request and will come back to you."
      />

      <Card>
        <CardBody className="space-y-3">
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm text-muted-foreground">Your reference</span>
            <Mono className="text-sm">{data.reference}</Mono>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm text-muted-foreground">Current stage</span>
            <span className="text-sm font-medium">{data.stage_label}</span>
          </div>
          <div className="flex items-baseline justify-between gap-3">
            <span className="text-sm text-muted-foreground">Expected by</span>
            <span className="text-sm">{formatDate(data.expected_date)}</span>
          </div>
        </CardBody>
      </Card>

      {/*
        A file refused on the way in is named here rather than swallowed. The
        request itself stood, so the message says which file and leaves the
        attachment panel below to try again.
      */}
      {refused ? (
        <Notice tone="warn" title="Some files did not go up">
          {refused}. Your request was raised without them. Every upload is scanned before it is
          stored, and a file that fails the scan or the type check is refused. Try again below.
        </Notice>
      ) : null}

      <Attachments requestId={requestId} />

      <Notice title="What happens next">
        Legal will assess your request and either accept it as a matter, answer it and close it,
        or come back to you for more information. You can follow it on your requests page without
        emailing anyone.
      </Notice>

      <Card>
        <CardBody className="space-y-3">
          <div className="text-sm font-semibold">You are finished here</div>
          <p className="text-sm leading-relaxed text-muted-foreground">
            Attach anything else you have first. Nothing else is required of you, and you will be
            told when the position changes.
          </p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <Button variant="primary" onClick={() => router.push("/portal/status")}>
              Track this request
            </Button>
            <Button onClick={() => router.push("/portal")}>Raise another request</Button>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
