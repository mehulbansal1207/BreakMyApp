import Link from "next/link";
import CopyButton from "@/components/CopyButton";

export default function GitHubActionDocs() {
  const yamlContent = `name: BreakMyApp Security Scan

on:
  pull_request:
    branches:
      - main
      - master

jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      issues: write
      pull-requests: write

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Start BreakMyApp scan
        id: start_scan
        run: |
          REPO_URL="\${{ github.server_url }}/\${{ github.repository }}"
          RESPONSE=$(curl -sf -X POST \\
            "https://breakmyapp-production-2ec7.up.railway.app/api/v1/scans/" \\
            -H "Content-Type: application/json" \\
            -d "{\\"repo_url\\": \\"$REPO_URL\\"}")
          SCAN_ID=$(echo "$RESPONSE" | jq -r '.id')
          echo "scan_id=$SCAN_ID" >> "$GITHUB_OUTPUT"

      - name: Wait for scan to complete
        id: wait_scan
        run: |
          SCAN_ID="\${{ steps.start_scan.outputs.scan_id }}"
          MAX_ATTEMPTS=120
          ATTEMPT=0
          while [ $ATTEMPT -lt $MAX_ATTEMPTS ]; do
            SUMMARY=$(curl -sf \\
              "https://breakmyapp-production-2ec7.up.railway.app/api/v1/scans/$SCAN_ID/summary")
            STATUS=$(echo "$SUMMARY" | jq -r '.status')
            if [ "$STATUS" != "pending" ] && [ "$STATUS" != "running" ]; then
              echo "summary=$SUMMARY" >> "$GITHUB_OUTPUT"
              break
            fi
            ATTEMPT=$((ATTEMPT + 1))
            sleep 10
          done

      - name: Post GitHub report
        if: github.event_name == 'pull_request'
        run: |
          SCAN_ID="\${{ steps.start_scan.outputs.scan_id }}"
          curl -sf -X POST \\
            "https://breakmyapp-production-2ec7.up.railway.app/api/v1/github/report/$SCAN_ID" \\
            -H "Content-Type: application/json" \\
            -d "{
              \\"token\\": \\"\${{ secrets.BREAKMYAPP_TOKEN }}\\",
              \\"owner\\": \\"\${{ github.repository_owner }}\\",
              \\"repo\\": \\"\${{ github.event.repository.name }}\\",
              \\"pr_number\\": \${{ github.event.pull_request.number }}
            }"

      - name: Print scan summary
        if: always()
        run: |
          SCORE=$(echo '\${{ steps.wait_scan.outputs.summary }}' | jq -r '.score // "N/A"')
          REPORT=$(echo '\${{ steps.wait_scan.outputs.summary }}' | jq -r '.report_url // "N/A"')
          echo "Score: $SCORE/100"
          echo "Report: $REPORT"`;

  return (
    <div className="max-w-4xl mx-auto px-6 py-10 bg-gray-950 min-h-screen text-gray-200">
      <Link href="/" className="inline-block mb-8 text-gray-400 hover:text-white transition">
        ← Back
      </Link>

      {/* 1. HERO SECTION */}
      <section className="mb-16">
        <h1 className="text-4xl md:text-5xl font-bold text-white mb-4">
          GitHub Action
        </h1>
        <p className="text-xl text-gray-400 mb-8 max-w-2xl">
          Automatically scan every pull request and create GitHub Issues for security findings.
        </p>
        <div className="flex flex-wrap gap-3">
          <span className="px-3 py-1 rounded-full bg-green-500/10 text-green-400 border border-green-500/20 text-sm font-medium">
            ✅ PR Comments
          </span>
          <span className="px-3 py-1 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 text-sm font-medium">
            🐛 Auto Issue Creation
          </span>
          <span className="px-3 py-1 rounded-full bg-blue-500/10 text-blue-400 border border-blue-500/20 text-sm font-medium">
            🔒 Security Scanning
          </span>
        </div>
      </section>

      {/* 2. HOW IT WORKS */}
      <section className="mb-16">
        <h2 className="text-2xl font-bold text-white mb-6">How it works</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="text-indigo-500 mb-4">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 21h10a2 2 0 002-2V9.414a1 1 0 00-.293-.707l-5.414-5.414A1 1 0 0012.586 3H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
              </svg>
            </div>
            <h3 className="font-semibold text-white mb-2">Step 1 — Add the workflow file</h3>
            <p className="text-gray-400 text-sm">Add a single YAML file to your repository</p>
          </div>
          
          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="text-indigo-500 mb-4">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7v8a2 2 0 002 2h6M8 7V5a2 2 0 012-2h4.586a1 1 0 01.707.293l4.414 4.414a1 1 0 01.293.707V15a2 2 0 01-2 2h-2M8 7H6a2 2 0 00-2 2v10a2 2 0 002 2h8a2 2 0 002-2v-2" />
              </svg>
            </div>
            <h3 className="font-semibold text-white mb-2">Step 2 — Open a Pull Request</h3>
            <p className="text-gray-400 text-sm">Every PR automatically triggers a security scan</p>
          </div>

          <div className="bg-gray-900 border border-gray-800 rounded-xl p-6">
            <div className="text-indigo-500 mb-4">
              <svg className="w-8 h-8" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
              </svg>
            </div>
            <h3 className="font-semibold text-white mb-2">Step 3 — Get Results</h3>
            <p className="text-gray-400 text-sm">Score posted as PR comment, issues created for findings</p>
          </div>
        </div>
      </section>

      {/* 3. SETUP INSTRUCTIONS */}
      <section>
        <h2 className="text-2xl font-bold text-white mb-6">Setup</h2>
        
        <div className="space-y-8">
          <div>
            <h3 className="text-xl font-semibold text-white mb-2">1. Create a GitHub Token</h3>
            <p className="text-gray-400 leading-relaxed">
              Go to GitHub → Settings → Developer Settings → Personal Access Tokens → Generate new token (classic). 
              Select the <code className="font-mono bg-gray-800 px-2 py-0.5 rounded text-indigo-400">repo</code> scope. Copy the token.
            </p>
          </div>

          <div>
            <h3 className="text-xl font-semibold text-white mb-2">2. Add Token as Repository Secret</h3>
            <p className="text-gray-400 leading-relaxed mb-2">
              Go to your repository → Settings → Secrets and variables → Actions → New repository secret.
            </p>
            <p className="text-gray-400">
              Name: <code className="font-mono bg-gray-800 px-2 py-0.5 rounded text-indigo-400">BREAKMYAPP_TOKEN</code><br />
              Value: (paste your token)
            </p>
          </div>

          <div>
            <h3 className="text-xl font-semibold text-white mb-2">3. Add the Workflow File</h3>
            <p className="text-gray-400 mb-4">
              Create this file in your repository:{" "}
              <code className="font-mono bg-gray-800 px-2 py-0.5 rounded text-indigo-400">
                .github/workflows/breakmyapp.yml
              </code>
            </p>
            
            <div className="relative">
              <pre className="bg-gray-900 border border-gray-800 rounded-xl p-6 font-mono text-sm text-gray-300 overflow-x-auto mb-4">
                <code>{yamlContent}</code>
              </pre>
              <div className="mt-4">
                <CopyButton text={yamlContent} />
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  );
}
