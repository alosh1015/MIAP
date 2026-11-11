import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type AdminUser, type Role } from "../api/client";
import { useAuth } from "../auth/AuthContext";
import { AdminSubnav, ROLE_LABEL } from "../components/shell/AppShell";
import {
  Badge,
  Button,
  Dialog,
  ErrorNote,
  Field,
  IconButton,
  Input,
  Panel,
  PageHeader,
  Select,
  Table,
  Td,
  Th,
  formatDay,
  prettyLabel,
} from "../components/ui";

export function AdminUsersPage() {
  const { user: me } = useAuth();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [editing, setEditing] = useState<AdminUser | null>(null);
  const [resetting, setResetting] = useState<AdminUser | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    api
      .listUsers()
      .then((data) => {
        setUsers(data);
        setError(null);
      })
      .catch((caught) => setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not load users"))
      .finally(() => setLoading(false));
  }, []);

  useEffect(load, [load]);

  async function toggleActive(user: AdminUser) {
    setError(null);
    try {
      await api.updateUser(user.id, { is_active: !user.is_active });
      load();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not update the account");
    }
  }

  return (
    <div>
      <PageHeader
        title="Users and roles"
        actions={
          <Button variant="primary" icon="plus" onClick={() => setCreateOpen(true)}>
            New user
          </Button>
        }
      />
      <AdminSubnav />
      <ErrorNote message={error} />

      <Panel>
        {loading && users.length === 0 ? (
          <p className="p-8 text-sm text-muted">Loading users…</p>
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>User</Th>
                <Th>Role</Th>
                <Th>Status</Th>
                <Th>Created</Th>
                <Th align="right">Actions</Th>
              </tr>
            </thead>
            <tbody>
              {users.map((user) => (
                <tr key={user.id} className="hover:bg-surface-2/60">
                  <Td>
                    <p className="font-medium text-ink">{user.display_name}</p>
                    <p className="mt-0.5 text-xs text-muted">{user.email}</p>
                  </Td>
                  <Td>
                    <Badge tone={user.role === "administrator" ? "neutral" : "petrol"}>{ROLE_LABEL[user.role]}</Badge>
                  </Td>
                  <Td>
                    <Badge tone={user.is_active ? "good" : "neutral"}>{user.is_active ? "Active" : "Inactive"}</Badge>
                  </Td>
                  <Td className="text-xs text-muted">{formatDay(user.created_at)}</Td>
                  <Td align="right">
                    <div className="flex justify-end gap-1">
                      <IconButton icon="settings" label="Edit user" onClick={() => setEditing(user)} />
                      <IconButton icon="lock" label="Reset password" onClick={() => setResetting(user)} />
                      {user.id !== me?.id ? (
                        <IconButton
                          icon={user.is_active ? "eye-off" : "check"}
                          label={user.is_active ? "Deactivate user" : "Reactivate user"}
                          onClick={() => toggleActive(user)}
                        />
                      ) : null}
                    </div>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Panel>

      <CreateUserDialog
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onCreated={() => {
          setCreateOpen(false);
          load();
        }}
      />
      <EditUserDialog
        user={editing}
        onClose={() => setEditing(null)}
        onSaved={() => {
          setEditing(null);
          load();
        }}
      />
      <ResetPasswordDialog
        user={resetting}
        onClose={() => setResetting(null)}
        onSaved={() => setResetting(null)}
      />
    </div>
  );
}

function CreateUserDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [email, setEmail] = useState("");
  const [displayName, setDisplayName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("clinician");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    setEmail("");
    setDisplayName("");
    setPassword("");
    setRole("clinician");
    setError(null);
  }, [open]);

  async function submit() {
    setBusy(true);
    setError(null);
    try {
      await api.createUser({
        email: email.trim(),
        display_name: displayName.trim(),
        password,
        role,
      });
      onCreated();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not create the user");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="New user"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button
            variant="primary"
            icon="plus"
            loading={busy}
            disabled={!email.trim() || !displayName.trim() || password.length < 8}
            onClick={submit}
          >
            Create user
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Display name">
          <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </Field>
        <Field label="Email">
          <Input type="email" value={email} onChange={(event) => setEmail(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Initial password" hint="At least 8 characters.">
            <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
          </Field>
          <Field label="Role">
            <Select value={role} onChange={(event) => setRole(event.target.value as Role)}>
              {(["clinician", "researcher", "administrator"] as Role[]).map((entry) => (
                <option key={entry} value={entry}>
                  {ROLE_LABEL[entry]}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <ErrorNote message={error} />
      </div>
    </Dialog>
  );
}

function EditUserDialog({
  user,
  onClose,
  onSaved,
}: {
  user: AdminUser | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [displayName, setDisplayName] = useState("");
  const [role, setRole] = useState<Role>("clinician");
  const [active, setActive] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setDisplayName(user.display_name);
    setRole(user.role);
    setActive(user.is_active);
    setError(null);
  }, [user]);

  async function save() {
    if (!user) return;
    setBusy(true);
    setError(null);
    try {
      await api.updateUser(user.id, { display_name: displayName.trim(), role, is_active: active });
      onSaved();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not update the user");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={user !== null}
      onClose={onClose}
      title="Edit user"
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} onClick={save}>
            Save changes
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="Display name">
          <Input value={displayName} onChange={(event) => setDisplayName(event.target.value)} />
        </Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Role">
            <Select value={role} onChange={(event) => setRole(event.target.value as Role)}>
              {(["clinician", "researcher", "administrator"] as Role[]).map((entry) => (
                <option key={entry} value={entry}>
                  {ROLE_LABEL[entry]}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Status" hint={prettyLabel(active ? "active" : "inactive")}>
            <Select value={active ? "active" : "inactive"} onChange={(event) => setActive(event.target.value === "active")}>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </Select>
          </Field>
        </div>
        <ErrorNote message={error} />
      </div>
    </Dialog>
  );
}

function ResetPasswordDialog({
  user,
  onClose,
  onSaved,
}: {
  user: AdminUser | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!user) return;
    setPassword("");
    setError(null);
  }, [user]);

  async function save() {
    if (!user) return;
    setBusy(true);
    setError(null);
    try {
      await api.resetPassword(user.id, password);
      onSaved();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.detail || caught.message : "Could not reset the password");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog
      open={user !== null}
      onClose={onClose}
      title={`Reset password${user ? ` · ${user.display_name}` : ""}`}
      footer={
        <>
          <Button onClick={onClose}>Cancel</Button>
          <Button variant="primary" loading={busy} disabled={password.length < 8} onClick={save}>
            Set password
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        <Field label="New password" hint="At least 8 characters.">
          <Input type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
        </Field>
        <ErrorNote message={error} />
      </div>
    </Dialog>
  );
}
