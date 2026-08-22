"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import { Attachments } from "@/components/app/attachments";
import { Card, CardBody, Mono, Notice, PageTitle, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { RequestStatus } from "@/lib/types";
import { formatDate } from "@/lib/utils";

export default function Submitted() {
  const { requestId } = useParams<{ requestId: string }>();
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

      <Attachments requestId={requestId} />

      <Notice title="What happens next">
        Legal will assess your request and either accept it as a matter, answer it and close it,
        or come back to you for more information. You can follow it on your requests page without
        emailing anyone.
      </Notice>

      <Link href="/portal/status" className="text-sm">
        See all my requests
      </Link>
    </div>
  );
}
