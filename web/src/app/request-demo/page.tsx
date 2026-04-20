import Link from "next/link";
import type { Route } from "next";
import { Card, CardBody, CardHeader } from "@/components/ui/card";

export default function RequestDemoPage() {
  return (
    <div className="min-h-screen bg-bg-base px-6 py-10 text-text-primary">
      <div className="mx-auto flex w-full max-w-2xl flex-col gap-6">
        <Link
          href="/"
          className="text-xs font-mono uppercase tracking-wide text-text-muted hover:text-text-secondary"
        >
          ← Back to home
        </Link>
        <Card>
          <CardHeader>
            <div>
              <h1 className="text-lg font-semibold text-text-primary">Request a demo</h1>
              <p className="mt-1 text-sm text-text-secondary">
                Tell us your target voice stack and we will run a tailored live walkthrough.
              </p>
            </div>
          </CardHeader>
          <CardBody className="space-y-4 text-sm text-text-secondary">
            <p>
              Email{" "}
              <a
                href="mailto:demo@botcheck.dev?subject=BotCheck%20Demo%20Request"
                className="text-brand hover:text-brand-hover"
              >
                demo@botcheck.dev
              </a>{" "}
              with:
            </p>
            <ul className="list-disc space-y-1 pl-5">
              <li>Primary IVR/provider (for example: LiveKit SIP + Genesys)</li>
              <li>Top 3 risks to test first (QA, PII, jailbreak, degradation)</li>
              <li>Preferred timezone and demo window</li>
            </ul>
            <p className="pt-2">
              Already onboarded?{" "}
                <Link href={"/login" as Route} className="text-brand hover:text-brand-hover">
                  Login to dashboard
                </Link>
              .
            </p>
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
