"use client";

import Link from "next/link";

import { Card, Empty, PageTitle, Spinner } from "@/components/ui";
import { useApi } from "@/lib/hooks";
import type { RequestType } from "@/lib/types";

const FALLBACK_CODE = "something_else";

export default function PortalHome() {
  const { data, loading, error } = useApi<RequestType[]>("/requests/types");

  const listed = (data ?? []).filter((type) => type.code !== FALLBACK_CODE);
  const fallback = (data ?? []).find((type) => type.code === FALLBACK_CODE);

  return (
    <div className="space-y-6">
      <PageTitle
        title="How can Legal help?"
        subtitle="Choose the option that best describes your request. We will only ask for the information Legal needs."
      />

      {loading ? (
        <Spinner />
      ) : error ? (
        <Empty title="The request types could not be loaded" detail={error.message} />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 sm:gap-4">
          {listed.map((type) => (
            <Link
              key={type.id}
              href={`/portal/new/${type.code}`}
              className="block no-underline text-foreground"
            >
              <Card className="h-full transition-colors hover:border-brand">
                <div className="p-4 sm:p-5">
                  <div className="text-base font-semibold">{type.business_label}</div>
                  {type.description ? (
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      {type.description}
                    </p>
                  ) : null}
                </div>
              </Card>
            </Link>
          ))}
        </div>
      )}

      {fallback ? (
        <Link
          href={`/portal/new/${fallback.code}`}
          className="block no-underline text-foreground"
        >
          <Card className="border-dashed transition-colors hover:border-brand">
            <div className="p-4 sm:p-5">
              <div className="text-base font-semibold">Something else</div>
              <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                Describe what you need from Legal.
              </p>
            </div>
          </Card>
        </Link>
      ) : null}
    </div>
  );
}
