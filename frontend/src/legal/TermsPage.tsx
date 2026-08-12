import { Link } from "react-router-dom";

import { LegalLayout, LegalSection } from "./LegalLayout";

export function TermsPage() {
  return (
    <LegalLayout title="Terms of Service" updated="August 9, 2026">
      <p>
        ZeroBudget is self-hosted software released under the GNU Affero General Public License
        v3 (AGPLv3). There is no ZeroBudget company. By using an instance of this software, you're
        agreeing to these terms with whoever operates that instance — not with the software's
        authors, unless they happen to be the same person.
      </p>

      <LegalSection title="License and no warranty">
        <p>
          The ZeroBudget software is provided under the AGPLv3, which — like most open-source
          licenses — disclaims warranties and liability. In short: the software is provided "as
          is," without warranty of any kind, and its authors are not liable for damages arising
          from its use, to the extent permitted by law. See the{" "}
          <a
            href="https://github.com/scevola44/zerobudget/blob/main/LICENSE"
            target="_blank"
            rel="noreferrer"
            className="text-indigo-600 dark:text-indigo-400 hover:underline"
          >
            LICENSE
          </a>{" "}
          file (AGPLv3 §15–16) for the full text.
        </p>
      </LegalSection>

      <LegalSection title="Your account">
        <p>
          ZeroBudget accounts use a local email and password — there's no sign-in with Google,
          Apple, or any other identity provider. Your password is hashed with bcrypt before
          storage. You're responsible for choosing a password you don't reuse elsewhere and for
          keeping it and your devices secure. Signing in issues a session token that's valid for a
          limited time (7 days by default); anyone who obtains that token can act as you until it
          expires.
        </p>
      </LegalSection>

      <LegalSection title="Bank linking">
        <p>
          Linking a bank account is optional. It's handled through Enable Banking, a third-party
          PSD2 provider, and is subject to Enable Banking's own terms and your bank's consent
          process, which are outside ZeroBudget's control. You can withdraw consent at any time
          through your bank or by disconnecting the account in ZeroBudget.
        </p>
      </LegalSection>

      <LegalSection title="Operator responsibility">
        <p>
          If you operate a ZeroBudget instance for yourself or others, you are responsible for
          that instance: its security, uptime, backups, and compliance with any laws that apply to
          you (such as data protection law, if you handle other people's data). The software's
          authors provide the code as-is and have no role in, or responsibility for, how any
          particular instance is run.
        </p>
      </LegalSection>

      <LegalSection title="Acceptable use">
        <p>
          Don't use ZeroBudget to break the law, and don't use its bank-linking features to abuse
          Enable Banking's systems or your bank's systems — for example, by connecting accounts
          you're not authorized to access, or by making automated requests beyond what normal use
          requires.
        </p>
      </LegalSection>

      <LegalSection title="No guarantee of availability">
        <p>
          ZeroBudget is self-hosted software with no service-level agreement, uptime guarantee, or
          support commitment from its authors. Availability of any given instance depends entirely
          on how and where it's deployed.
        </p>
      </LegalSection>

      <LegalSection title="Changes">
        <p>
          The software and these terms may change over time as new versions are released.
          Operators choose when to upgrade their own instances, so a given instance may not
          reflect the latest version of the software or of this document.
        </p>
      </LegalSection>

      <LegalSection title="Governing basis">
        <p>
          The AGPLv3 governs your rights to use, modify, and distribute the ZeroBudget software
          itself. These terms don't replace or override the AGPLv3, and they aren't a substitute
          for any separate terms an operator may set for their own users.
        </p>
      </LegalSection>

      <LegalSection title="Contact">
        <p>
          For questions about using a specific instance, contact the person or organization that
          operates it. For questions about the software itself, see the project's{" "}
          <a
            href="https://github.com/scevola44/zerobudget"
            target="_blank"
            rel="noreferrer"
            className="text-indigo-600 dark:text-indigo-400 hover:underline"
          >
            source repository
          </a>
          .
        </p>
      </LegalSection>

      <p className="text-xs text-stone-500 dark:text-stone-500">
        See also the{" "}
        <Link to="/privacy" className="text-indigo-600 dark:text-indigo-400 hover:underline">
          Privacy Policy
        </Link>
        .
      </p>
    </LegalLayout>
  );
}
