import { Navigate, Route, Routes } from "react-router-dom";

import { LoginPage } from "./auth/LoginPage";
import { RegisterPage } from "./auth/RegisterPage";
import { RequireAuth } from "./auth/RequireAuth";
import { Layout } from "./components/Layout";
import { AccountDetailPage } from "./pages/AccountDetailPage";
import { AccountsPage } from "./pages/AccountsPage";
import { BankingCallbackPage } from "./pages/BankingCallbackPage";
import { BudgetPage } from "./pages/BudgetPage";
import { CategoriesPage } from "./pages/CategoriesPage";
import { TransactionsPage } from "./pages/TransactionsPage";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/"
        element={
          <RequireAuth>
            <Layout>
              <Navigate to="/budget" replace />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/budget"
        element={
          <RequireAuth>
            <Layout>
              <BudgetPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/accounts"
        element={
          <RequireAuth>
            <Layout>
              <AccountsPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/banking/callback"
        element={
          <RequireAuth>
            <Layout>
              <BankingCallbackPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/accounts/:id"
        element={
          <RequireAuth>
            <Layout>
              <AccountDetailPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/categories"
        element={
          <RequireAuth>
            <Layout>
              <CategoriesPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route
        path="/transactions"
        element={
          <RequireAuth>
            <Layout>
              <TransactionsPage />
            </Layout>
          </RequireAuth>
        }
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
