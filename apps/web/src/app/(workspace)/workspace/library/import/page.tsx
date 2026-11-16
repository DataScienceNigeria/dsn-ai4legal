"use client";

import Link from "next/link";

import { useRoles } from "@/components/app/session";
import { WorkbookImportScreen } from "@/components/app/workbook-import";
import { Button, PageTitle, Refusal } from "@/components/ui";

export default function LibraryImport() {
  const { has } = useRoles();

  if (!has("counsel", "head_of_legal", "admin")) {
    return (
      <Refusal
        title="The clause library is not available to you"
        reason="Importing the playbook and clause library is for legal staff."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Import the playbook workbook"
        subtitle="Check the legal team's workbook row by row, then apply it as drafts. The Head of Legal publishes each playbook before any of it is house position."
        actions={
          <Link href="/workspace/library">
            <Button size="sm">Back to the library</Button>
          </Link>
        }
      />
      <WorkbookImportScreen />
    </div>
  );
}
