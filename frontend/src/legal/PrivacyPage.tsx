import { Link } from "react-router-dom";

import { LegalLayout, LegalSection } from "./LegalLayout";

export function PrivacyPage() {
  return (
    <LegalLayout title="Privacy Policy" updated="August 9, 2026">
      <p>
        ZeroBudget is self-hosted software, released under the AGPLv3 license. There is no company
        operating a shared ZeroBudget service, and nothing about your data ever reaches the
        software's authors. This page describes what the ZeroBudget software itself does with
        data when someone runs an instance of it. If you're using an instance that someone else
        deployed for you, they — the operator — control that data, not the authors of the code.
      </p>

      <LegalSection title="Who controls your data">
        <p>
          The person or organization running the ZeroBudget instance you use is the data
          controller for that instance. They decide where it's hosted, who can access the
          database and backups, and how long data is kept. The software's authors have no access
          to any deployed instance and receive no data, logs, or analytics from it.
        </p>
      </LegalSection>

      <LegalSection title="What we store">
        <ul className="list-disc pl-5 space-y-1">
          <li>Your account email address and a bcrypt hash of your password — the plain password is never stored.</li>
          <li>Budget accounts you create: name, type, and, for bank-linked accounts, a masked identifier (the last few characters of the IBAN), the bank product name, and connection metadata.</li>
          <li>Transactions: date, payee, memo, amount, and an identifier used to avoid duplicate imports.</li>
          <li>Your budget and category configuration.</li>
        </ul>
        <p>Account balances are calculated from your transactions each time they're needed — they are not stored as a separate figure.</p>
      </LegalSection>

      <LegalSection title="Bank linking via Enable Banking">
        <p>
          Connecting a bank account uses{" "}
          <a
            href="https://enablebanking.com"
            target="_blank"
            rel="noreferrer"
            className="text-indigo-600 dark:text-indigo-400 hover:underline"
          >
            Enable Banking
          </a>
          , a licensed EU PSD2 account-information provider. When you link a bank, you're
          redirected to authenticate directly on your bank's own website or app — ZeroBudget never
          sees or handles your bank username or password. After you approve access, your bank
          sends ZeroBudget back a consent session, which is what allows transactions to be synced.
        </p>
        <p>
          This bank-linking flow currently supports EUR accounts only. Consent lasts up to 180
          days, after which you'll need to reauthorize it. You can revoke access at any time,
          either from your bank's own online banking portal or by disconnecting the account in
          ZeroBudget.
        </p>
      </LegalSection>

      <LegalSection title="Encryption — what is and isn't protected">
        <p>We'd rather tell you exactly what's protected than let you assume everything is:</p>
        <ul className="list-disc pl-5 space-y-1">
          <li>The bank consent session created by Enable Banking is encrypted at rest in the database.</li>
          <li>Other stored data — your email, transactions, and account details — is stored as plain fields in the database. Protecting the database itself (disk encryption, access control, backup security) is the responsibility of whoever operates your instance.</li>
          <li>Your password is never stored in plain text; it's hashed with bcrypt, which is one-way and can't be reversed to recover your password.</li>
          <li>After you sign in, your session is a token (JWT) held in your browser's local storage, not a cookie. Anyone with access to your browser's storage on a shared or compromised device could use it until it expires.</li>
        </ul>
      </LegalSection>

      <LegalSection title="Transport security">
        <p>
          Communication between ZeroBudget's backend and Enable Banking always uses HTTPS.
          Whether traffic between your browser and your ZeroBudget instance is encrypted (HTTPS)
          depends on how the operator has deployed it — ZeroBudget does not enforce this itself.
          If you operate an instance, put it behind HTTPS if it's reachable over any network you
          don't fully trust.
        </p>
      </LegalSection>

      <LegalSection title="No analytics or tracking">
        <p>
          ZeroBudget does not include analytics, advertising trackers, or error/crash-reporting
          services. The only outbound network calls it makes with your data are to Enable Banking,
          to sync your linked bank accounts. Container image updates are pulled from GitHub's
          container registry, which does not involve your data.
        </p>
      </LegalSection>

      <LegalSection title="No email features">
        <p>
          ZeroBudget does not currently send email of any kind — there's no password-reset email
          or other transactional email. Keep your password somewhere safe, since there's no
          automated way to recover it if it's lost.
        </p>
      </LegalSection>

      <LegalSection title="Data retention and deletion">
        <p>
          Your data stays in the database until the operator of your instance deletes it — for
          example by removing your account, deleting specific records, or tearing down the
          instance entirely. ZeroBudget does not currently provide a self-service "export my data"
          or "delete my account" feature in the app itself; requests like that go to whoever
          operates your instance.
        </p>
      </LegalSection>

      <LegalSection title="Your rights">
        <p>
          If you're in the EU or another jurisdiction with data protection rights (such as GDPR
          access, correction, or erasure rights), those rights are owed to you by the operator of
          your instance, since they are the data controller. Contact them directly. The authors of
          the ZeroBudget software are not a data processor or controller for any instance they
          don't operate themselves.
        </p>
      </LegalSection>

      <LegalSection title="Changes to this policy">
        <p>
          This page may be updated as the software changes. Check the "Last updated" date at the
          top. There's no mailing list or notification system for changes — if you operate an
          instance, review this page after upgrading.
        </p>
      </LegalSection>

      <LegalSection title="Contact">
        <p>
          For questions about your data, contact the operator of your ZeroBudget instance — they
          are the ones who can act on it. If you operate your own instance and have questions
          about how the software works, see the project's{" "}
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
        <Link to="/terms" className="text-indigo-600 dark:text-indigo-400 hover:underline">
          Terms of Service
        </Link>
        .
      </p>
    </LegalLayout>
  );
}
