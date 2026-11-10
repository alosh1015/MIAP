import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";

export function LoginPage() {
  const { user, login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (user) navigate("/", { replace: true });
  }, [user, navigate]);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate("/", { replace: true });
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Sign-in failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen bg-slate-100 lg:grid-cols-[1.1fr_1fr]">
      <div className="hidden flex-col justify-between bg-ink-900 p-12 text-slate-300 lg:flex">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-clinical-500 text-lg font-bold text-white">
            M
          </div>
          <div>
            <p className="text-base font-semibold text-white">MIAP</p>
            <p className="text-xs text-slate-500">Medical Image AI Pipeline</p>
          </div>
        </div>
        <div className="max-w-md">
          <h2 className="text-3xl font-semibold leading-tight text-white">
            De-identified images in. Traceable decision support out.
          </h2>
          <p className="mt-5 text-sm leading-relaxed text-slate-400">
            Chest X-ray classification and mammogram four-view review, built for a low-resource
            hospital workflow. Every result carries its model version, input digest and audit trail.
          </p>
          <ul className="mt-8 space-y-3 text-sm text-slate-400">
            <li className="flex gap-3">
              <span className="text-clinical-500">•</span> PS3.15 de-identification before any file is stored
            </li>
            <li className="flex gap-3">
              <span className="text-clinical-500">•</span> Append-only hash-chained audit log
            </li>
            <li className="flex gap-3">
              <span className="text-clinical-500">•</span> Role-based access; administrators never receive pixels
            </li>
          </ul>
        </div>
        <p className="text-xs text-slate-600">
          Decision support only. Not a diagnostic device. Reviewed by a qualified clinician before any
          clinical action.
        </p>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-8 lg:hidden">
            <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-clinical-600 text-lg font-bold text-white">
              M
            </div>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
          <p className="mt-1 text-sm text-slate-500">Use the account issued by your MIAP administrator.</p>

          <form className="mt-8 space-y-4" onSubmit={submit}>
            <label className="block">
              <span className="text-xs font-medium text-slate-600">Email</span>
              <input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                className="focus-ring mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
                placeholder="name@hospital.org"
              />
            </label>
            <label className="block">
              <span className="text-xs font-medium text-slate-600">Password</span>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="focus-ring mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm"
              />
            </label>
            {error ? (
              <div className="rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700" role="alert">
                {error}
              </div>
            ) : null}
            <button
              type="submit"
              disabled={busy}
              className="focus-ring w-full rounded-lg bg-clinical-600 px-3 py-2.5 text-sm font-semibold text-white hover:bg-clinical-700 disabled:opacity-60"
            >
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>

          {import.meta.env.DEV ? (
            <div className="mt-8 rounded-lg border border-dashed border-slate-300 bg-white p-3 text-[11px] text-slate-500">
              <p className="font-medium text-slate-600">Demo accounts (development only)</p>
              <p className="mt-1 font-mono">clinician@miap.local · miap-demo-2026</p>
              <p className="font-mono">researcher@miap.local · miap-demo-2026</p>
              <p className="font-mono">admin@miap.local · miap-demo-2026</p>
              <p className="mt-2">
                Create them with <code className="rounded bg-slate-100 px-1">python -m app.seed</code>.
              </p>
            </div>
          ) : null}

          <p className="mt-8 text-center text-xs text-slate-400">
            <Link to="/" className="hover:text-slate-600">
              MIAP
            </Link>{" "}
            · decision support, not a diagnosis
          </p>
        </div>
      </div>
    </div>
  );
}
