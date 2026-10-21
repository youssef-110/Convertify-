// Windows 11 right-click menu entry ("Convert with Convertify" > Open in Convertify... / PDF / DOCX / PPTX).
// Explorer loads this through the package in AppxManifest.xml. What to show comes from menu.txt next to
// this DLL, written by shell.py:
//   line 1:           the command that starts the app, e.g. "C:\...\pythonw.exe" "C:\...\gui.pyw"
//   following lines:  ext <TAB> target <TAB> label      (target "*more" = "Open in Convertify")
// Build: g++ -shared -O2 -static -o ConvertifyMenu.dll menu.cpp menu.def -lole32 -luuid -lshell32 -lshlwapi
#include <windows.h>
#include <shobjidl.h>
#include <shlwapi.h>
#include <new>
#include <string>
#include <vector>

// {2BADD1AC-1C7A-44F4-8C95-42779315F5FE}
static const CLSID CLSID_Menu = {0x2badd1ac, 0x1c7a, 0x44f4, {0x8c, 0x95, 0x42, 0x77, 0x93, 0x15, 0xf5, 0xfe}};
static HMODULE g_module;
static LONG g_objects;

struct Entry { std::wstring ext, target, label; };
struct Config { std::wstring launcher, folder; std::vector<Entry> entries; };

static std::wstring widen(const std::string& s) {
    int n = MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), nullptr, 0);
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, 0, s.data(), (int)s.size(), &w[0], n);
    return w;
}

static Config load_config() {  // read on every use, so re-running install.bat takes effect at once
    Config c;
    wchar_t path[MAX_PATH];
    GetModuleFileNameW(g_module, path, MAX_PATH);
    PathRemoveFileSpecW(path);
    c.folder = path;
    HANDLE f = CreateFileW((c.folder + L"\\menu.txt").c_str(), GENERIC_READ, FILE_SHARE_READ, nullptr, OPEN_EXISTING, 0, nullptr);
    if (f == INVALID_HANDLE_VALUE) return c;
    std::string data;
    char buf[4096];
    DWORD got;
    while (ReadFile(f, buf, sizeof buf, &got, nullptr) && got) data.append(buf, got);
    CloseHandle(f);
    std::wstring text = widen(data);
    size_t start = 0;
    bool first = true;
    while (start < text.size()) {
        size_t end = text.find(L'\n', start);
        if (end == std::wstring::npos) end = text.size();
        std::wstring line = text.substr(start, end - start);
        if (!line.empty() && line.back() == L'\r') line.pop_back();
        start = end + 1;
        if (first) { c.launcher = line; first = false; continue; }
        size_t a = line.find(L'\t'), b = line.find(L'\t', a + 1);
        if (a == std::wstring::npos || b == std::wstring::npos) continue;
        c.entries.push_back({line.substr(0, a), line.substr(a + 1, b - a - 1), line.substr(b + 1)});
    }
    return c;
}

static std::vector<std::wstring> selected_paths(IShellItemArray* items) {
    std::vector<std::wstring> out;
    DWORD count = 0;
    if (!items || FAILED(items->GetCount(&count))) return out;
    for (DWORD i = 0; i < count; i++) {
        IShellItem* item;
        if (FAILED(items->GetItemAt(i, &item))) continue;
        PWSTR p;
        if (SUCCEEDED(item->GetDisplayName(SIGDN_FILESYSPATH, &p))) { out.push_back(p); CoTaskMemFree(p); }
        item->Release();
    }
    return out;
}

static std::wstring ext_of(const std::wstring& path) {
    const wchar_t* e = PathFindExtensionW(path.c_str());
    std::wstring ext = *e ? e + 1 : L"";
    for (auto& ch : ext) ch = towlower(ch);
    return ext;
}

static bool offers(const Config& c, const std::wstring& ext, const std::wstring& target) {
    for (auto& e : c.entries) if (e.ext == ext && e.target == target) return true;
    return false;
}

static void launch(const std::wstring& args) {
    std::wstring cmd = args;
    STARTUPINFOW si = {sizeof si};
    PROCESS_INFORMATION pi;
    if (CreateProcessW(nullptr, &cmd[0], nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi)) {
        CloseHandle(pi.hThread);
        CloseHandle(pi.hProcess);
    }
}

class Command;

class Enum : public IEnumExplorerCommand {
    LONG refs = 1;
    std::vector<IExplorerCommand*> items;
    size_t pos = 0;
public:
    explicit Enum(std::vector<IExplorerCommand*> v) : items(std::move(v)) { InterlockedIncrement(&g_objects); }
    ~Enum() { for (auto* i : items) i->Release(); InterlockedDecrement(&g_objects); }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) {
        if (riid == IID_IUnknown || riid == IID_IEnumExplorerCommand) { *ppv = this; AddRef(); return S_OK; }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP_(ULONG) AddRef() { return InterlockedIncrement(&refs); }
    IFACEMETHODIMP_(ULONG) Release() { LONG r = InterlockedDecrement(&refs); if (!r) delete this; return r; }
    IFACEMETHODIMP Next(ULONG n, IExplorerCommand** out, ULONG* fetched) {
        ULONG i = 0;
        for (; i < n && pos < items.size(); i++, pos++) { out[i] = items[pos]; out[i]->AddRef(); }
        if (fetched) *fetched = i;
        return i == n ? S_OK : S_FALSE;
    }
    IFACEMETHODIMP Skip(ULONG n) { pos += n; return pos <= items.size() ? S_OK : S_FALSE; }
    IFACEMETHODIMP Reset() { pos = 0; return S_OK; }
    IFACEMETHODIMP Clone(IEnumExplorerCommand** out) { *out = nullptr; return E_NOTIMPL; }
};

// One class for the parent entry (target empty) and each choice under it.
class Command : public IExplorerCommand {
    LONG refs = 1;
    std::wstring target, label;
public:
    Command(std::wstring t, std::wstring l) : target(std::move(t)), label(std::move(l)) { InterlockedIncrement(&g_objects); }
    ~Command() { InterlockedDecrement(&g_objects); }
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) {
        if (riid == IID_IUnknown || riid == IID_IExplorerCommand) { *ppv = this; AddRef(); return S_OK; }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP_(ULONG) AddRef() { return InterlockedIncrement(&refs); }
    IFACEMETHODIMP_(ULONG) Release() { LONG r = InterlockedDecrement(&refs); if (!r) delete this; return r; }

    IFACEMETHODIMP GetTitle(IShellItemArray*, LPWSTR* name) {
        return SHStrDupW(target.empty() ? L"Convert with Convertify" : label.c_str(), name);
    }
    IFACEMETHODIMP GetIcon(IShellItemArray*, LPWSTR* icon) {
        if (!target.empty()) { *icon = nullptr; return E_NOTIMPL; }
        return SHStrDupW((load_config().folder + L"\\..\\assets\\icon.ico").c_str(), icon);
    }
    IFACEMETHODIMP GetToolTip(IShellItemArray*, LPWSTR* tip) { *tip = nullptr; return E_NOTIMPL; }
    IFACEMETHODIMP GetCanonicalName(GUID* guid) { *guid = CLSID_Menu; return S_OK; }
    IFACEMETHODIMP GetFlags(EXPCMDFLAGS* flags) {
        *flags = target.empty() ? ECF_HASSUBCOMMANDS : (target == L"*more" ? ECF_SEPARATORAFTER : ECF_DEFAULT);
        return S_OK;
    }
    IFACEMETHODIMP GetState(IShellItemArray* items, BOOL, EXPCMDSTATE* state) {
        // Show an entry only if every selected file can be converted that way.
        Config c = load_config();
        auto paths = selected_paths(items);
        // The parent and "More formats" show for any supported file (each has a "*more" line).
        std::wstring need = (target.empty() || target == L"*more") ? L"*more" : target;
        bool ok = !paths.empty();
        for (auto& p : paths)
            if (!offers(c, ext_of(p), need)) ok = false;
        *state = ok ? ECS_ENABLED : ECS_HIDDEN;
        return S_OK;
    }
    IFACEMETHODIMP Invoke(IShellItemArray* items, IBindCtx*) {
        Config c = load_config();
        auto paths = selected_paths(items);
        if (c.launcher.empty() || paths.empty()) return E_FAIL;
        if (target == L"*more") {  // one window with every selected file
            std::wstring args = c.launcher;
            for (auto& p : paths) args += L" \"" + p + L"\"";
            launch(args);
        } else {
            for (auto& p : paths) launch(c.launcher + L" --convert " + target + L" \"" + p + L"\"");
        }
        return S_OK;
    }
    IFACEMETHODIMP EnumSubCommands(IEnumExplorerCommand** out) {
        if (!target.empty()) { *out = nullptr; return E_NOTIMPL; }
        // Every choice that appears for any file type, in menu.txt order; GetState hides the ones that don't fit.
        Config c = load_config();
        std::vector<IExplorerCommand*> subs;
        std::vector<std::wstring> seen;
        for (auto& e : c.entries) {
            bool dup = false;
            for (auto& s : seen) if (s == e.target) dup = true;
            if (dup || e.target == L"*more") continue;
            seen.push_back(e.target);
            subs.push_back(new (std::nothrow) Command(e.target, e.label));
        }
        subs.push_back(new (std::nothrow) Command(L"*more", L"More formats\u2026"));
        *out = new (std::nothrow) Enum(subs);
        return *out ? S_OK : E_OUTOFMEMORY;
    }
};

class Factory : public IClassFactory {
public:
    IFACEMETHODIMP QueryInterface(REFIID riid, void** ppv) {
        if (riid == IID_IUnknown || riid == IID_IClassFactory) { *ppv = this; return S_OK; }
        *ppv = nullptr;
        return E_NOINTERFACE;
    }
    IFACEMETHODIMP_(ULONG) AddRef() { return 2; }
    IFACEMETHODIMP_(ULONG) Release() { return 1; }
    IFACEMETHODIMP CreateInstance(IUnknown* outer, REFIID riid, void** ppv) {
        if (outer) return CLASS_E_NOAGGREGATION;
        Command* c = new (std::nothrow) Command(L"", L"");
        if (!c) return E_OUTOFMEMORY;
        HRESULT hr = c->QueryInterface(riid, ppv);
        c->Release();
        return hr;
    }
    IFACEMETHODIMP LockServer(BOOL lock) { lock ? InterlockedIncrement(&g_objects) : InterlockedDecrement(&g_objects); return S_OK; }
};
static Factory g_factory;

extern "C" {
BOOL WINAPI DllMain(HINSTANCE h, DWORD reason, LPVOID) {
    if (reason == DLL_PROCESS_ATTACH) { g_module = h; DisableThreadLibraryCalls(h); }
    return TRUE;
}
HRESULT WINAPI DllGetClassObject(REFCLSID clsid, REFIID riid, void** ppv) {
    if (clsid != CLSID_Menu) { *ppv = nullptr; return CLASS_E_CLASSNOTAVAILABLE; }
    return g_factory.QueryInterface(riid, ppv);
}
HRESULT WINAPI DllCanUnloadNow() { return g_objects ? S_FALSE : S_OK; }
}
