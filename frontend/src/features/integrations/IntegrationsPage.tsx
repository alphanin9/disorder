import { ClaudeAuthCard } from "./ClaudeAuthCard";
import { CodexAuthCard } from "./CodexAuthCard";
import { CTFdImportCard } from "./CTFdImportCard";

export function IntegrationsPage() {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <CodexAuthCard />
      <ClaudeAuthCard />
      <CTFdImportCard />
    </div>
  );
}
