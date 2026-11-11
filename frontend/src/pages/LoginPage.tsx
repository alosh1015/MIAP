import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { Logo } from "../components/icons";
import { Button, ErrorNote, Input } from "../components/ui";

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
    <div className="grid min-h-screen bg-paper lg:grid-cols-[1fr_1.1fr]">
      <div className="brand-panel hidden flex-col justify-between p-10 lg:flex">
        <div className="flex items-center gap-3">
          <Logo size={34} />
          <span className="text-sm font-medium">MIAP</span>
        </div>
        <div>
          <p className="max-w-[25rem] text-2xl font-medium leading-snug">
            De-identified images in. Traceable decision support out.
          </p>
          <p className="mt-6 max-w-[24rem] text-xs leading-relaxed text-paper/70">
            Decision support only, not a diagnostic device. A qualified clinician reviews every image and
            patient. MIAP does not screen for tuberculosis.
          </p>
        </div>
        <p className="text-xs text-paper/50">Mbarara University of Science and Technology</p>
      </div>

      <div className="flex items-center justify-center px-6 py-12">
        <div className="w-full max-w-sm">
          <div className="mb-10 lg:hidden">
            <Logo size={34} />
          </div>
          <h1 className="text-2xl font-semibold text-ink">Sign in</h1>

          <form className="mt-8 space-y-4" onSubmit={submit}>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted">Email</span>
              <Input
                type="email"
                required
                autoComplete="username"
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder="name@hospital.org"
              />
            </label>
            <label className="block">
              <span className="mb-1.5 block text-xs font-medium text-muted">Password</span>
              <Input
                type="password"
                required
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
              />
            </label>
            <ErrorNote message={error} />
            <Button type="submit" variant="primary" loading={busy} className="w-full">
              {busy ? "Signing in…" : "Sign in"}
            </Button>
          </form>

          {import.meta.env.DEV ? (
            <div className="mt-10">
              <p className="text-xs font-medium text-ink">Demo accounts</p>
              <ul className="mt-2 space-y-1 font-mono text-xs text-muted">
                <li>clinician@miap.local · miap-demo-2026</li>
                <li>researcher@miap.local · miap-demo-2026</li>
                <li>admin@miap.local · miap-demo-2026</li>
              </ul>
            </div>
          ) : null}

          <p className="mt-8 text-xs leading-relaxed text-muted">
            Synthetic or consented, de-identified images only until the ethics and data-protection review is
            complete.
          </p>
        </div>
      </div>
    </div>
  );
}
