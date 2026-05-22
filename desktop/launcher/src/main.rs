#![cfg_attr(target_os = "windows", windows_subsystem = "windows")]

use directories::ProjectDirs;
use rand::RngCore;
use serde::Deserialize;
use std::env;
use std::ffi::OsStr;
use std::fs::{self, OpenOptions};
use std::net::TcpListener;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::thread::sleep;
use std::time::{Duration, Instant, SystemTime};

const PREFERRED_PORT: u16 = 18080;
const RUNTIME_FILE_NAME: &str = "runtime.json";
const LAUNCHER_TOKEN_HEADER: &str = "X-ACE-Launcher-Token";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(15);
const STARTUP_LOCK_TIMEOUT: Duration = Duration::from_secs(20);
const STARTUP_LOCK_STALE_AFTER: Duration = Duration::from_secs(30);
const STATUS_POLL_INTERVAL: Duration = Duration::from_millis(100);
const STATUS_REQUEST_TIMEOUT: Duration = Duration::from_millis(800);

type LauncherResult<T> = Result<T, String>;

#[derive(Debug, serde::Deserialize, serde::Serialize)]
struct RuntimeInfo {
    pid: u32,
    port: u16,
    token: String,
}

struct LaunchedServer {
    runtime: RuntimeInfo,
    child: Child,
}

struct StartupLock {
    path: PathBuf,
}

impl Drop for StartupLock {
    fn drop(&mut self) {
        let _ = fs::remove_file(&self.path);
    }
}


#[derive(Debug, Deserialize)]
struct RuntimeStatus {
    enabled: bool,
    authenticated: bool,
    active_tabs: usize,
}

fn main() {
    if let Err(error) = run() {
        eprintln!("ACE launcher error: {error}");
        std::process::exit(1);
    }
}

fn run() -> LauncherResult<()> {
    let current_dir = env::current_dir().map_err(|error| format!("failed to read current directory: {error}"))?;
    let mut open_path = extract_ace_path_from_args(env::args().skip(1), &current_dir);

    #[cfg(target_os = "macos")]
    if open_path.is_none() {
        open_path = macos_document_open::wait_for_document_open(Duration::from_millis(200));
    }

    let runtime_file = match env::var_os("ACE_TEST_RUNTIME_FILE") {
        Some(path) => PathBuf::from(path),
        None => runtime_file_path()?,
    };
    let _startup_lock = acquire_startup_lock(&runtime_file)?;

    let (runtime, launched_child) = if open_path.is_some() {
        let launched = start_server(&runtime_file)?;
        (launched.runtime, Some(launched.child))
    } else {
        match reusable_runtime_from_file(&runtime_file, open_path.as_deref()) {
            Some(runtime) => (runtime, None),
            None => {
                let launched = start_server(&runtime_file)?;
                (launched.runtime, Some(launched.child))
            }
        }
    };

    if let Err(error) = wait_for_runtime(&runtime)
        .and_then(|()| open_browser_for_runtime(&runtime, open_path.as_deref()))
    {
        cleanup_failed_launch(launched_child, &runtime_file, &runtime);
        return Err(error);
    }

    Ok(())
}

fn open_browser_for_runtime(runtime: &RuntimeInfo, open_path: Option<&Path>) -> LauncherResult<()> {
    let url = launch_url(runtime.port, &runtime.token, open_path);
    if env::var_os("ACE_TEST_SUPPRESS_BROWSER").is_some() {
        println!("{url}");
        return Ok(());
    }
    webbrowser::open(&url).map_err(|error| format!("failed to open default browser at {url}: {error}"))
}

fn cleanup_failed_launch(child: Option<Child>, runtime_file: &Path, runtime: &RuntimeInfo) {
    if let Some(mut child) = child {
        let _ = child.kill();
        let _ = child.wait();
        if runtime_file_matches(runtime_file, runtime) {
            let _ = fs::remove_file(runtime_file);
        }
    }
}

fn startup_lock_path(runtime_file: &Path) -> PathBuf {
    runtime_file.with_extension("lock")
}

fn acquire_startup_lock(runtime_file: &Path) -> LauncherResult<StartupLock> {
    if let Some(parent) = runtime_file.parent() {
        fs::create_dir_all(parent).map_err(|error| {
            format!(
                "failed to create runtime metadata directory {}: {error}",
                parent.display()
            )
        })?;
    }
    let lock_path = startup_lock_path(runtime_file);
    let deadline = Instant::now() + STARTUP_LOCK_TIMEOUT;
    loop {
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&lock_path)
        {
            Ok(mut file) => {
                let _ = std::io::Write::write_all(
                    &mut file,
                    format!("{}\n", std::process::id()).as_bytes(),
                );
                return Ok(StartupLock { path: lock_path });
            }
            Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => {
                if startup_lock_is_stale(&lock_path) {
                    let _ = fs::remove_file(&lock_path);
                    continue;
                }
                if Instant::now() >= deadline {
                    return Err(format!(
                        "timed out waiting for launcher startup lock {}",
                        lock_path.display()
                    ));
                }
                sleep(Duration::from_millis(100));
            }
            Err(error) => {
                return Err(format!(
                    "failed to create launcher startup lock {}: {error}",
                    lock_path.display()
                ));
            }
        }
    }
}

fn startup_lock_is_stale(lock_path: &Path) -> bool {
    let modified = match fs::metadata(lock_path).and_then(|meta| meta.modified()) {
        Ok(modified) => modified,
        Err(_) => return true,
    };
    match SystemTime::now().duration_since(modified) {
        Ok(elapsed) => elapsed > STARTUP_LOCK_STALE_AFTER,
        Err(_) => false,
    }
}

fn runtime_file_path() -> LauncherResult<PathBuf> {
    let dirs = ProjectDirs::from("au.edu.sydney", "ACE", "ACE")
        .ok_or_else(|| "failed to locate a per-user ACE runtime directory".to_string())?;
    Ok(dirs.data_local_dir().join(RUNTIME_FILE_NAME))
}

fn reusable_runtime_from_file(runtime_file: &Path, open_path: Option<&Path>) -> Option<RuntimeInfo> {
    let bytes = fs::read(runtime_file).ok()?;
    let runtime = match serde_json::from_slice::<RuntimeInfo>(&bytes) {
        Ok(runtime) => runtime,
        Err(_) => {
            let _ = fs::remove_file(runtime_file);
            return None;
        }
    };
    let status = match read_runtime_status(&runtime) {
        Some(status) => status,
        None => {
            let _ = fs::remove_file(runtime_file);
            return None;
        }
    };
    if !status.enabled || !status.authenticated {
        let _ = fs::remove_file(runtime_file);
        return None;
    }
    if open_path.is_some() && status.active_tabs > 0 {
        return None;
    }
    Some(runtime)
}

fn read_runtime_status(runtime: &RuntimeInfo) -> Option<RuntimeStatus> {
    let url = format!(
        "http://127.0.0.1:{}/api/runtime/status",
        runtime.port
    );
    let request = ureq::get(&url)
        .header(LAUNCHER_TOKEN_HEADER, runtime.token.as_str())
        .config()
        .timeout_global(Some(STATUS_REQUEST_TIMEOUT))
        .build();
    let mut response = request.call().ok()?;
    response
        .body_mut()
        .with_config()
        .limit(2048)
        .read_json::<RuntimeStatus>()
        .ok()
}

fn runtime_file_matches(runtime_file: &Path, runtime: &RuntimeInfo) -> bool {
    let bytes = match fs::read(runtime_file) {
        Ok(bytes) => bytes,
        Err(_) => return false,
    };
    match serde_json::from_slice::<RuntimeInfo>(&bytes) {
        Ok(existing) => {
            existing.pid == runtime.pid
                && existing.port == runtime.port
                && existing.token == runtime.token
        }
        Err(_) => false,
    }
}

fn start_server(runtime_file: &Path) -> LauncherResult<LaunchedServer> {
    let server_binary = match env::var_os("ACE_TEST_SERVER_BINARY") {
        Some(path) => PathBuf::from(path),
        None => locate_server_binary()?,
    };
    let port = choose_port()?;
    let token = generate_token();
    let idle_timeout = env::var("ACE_TEST_IDLE_TIMEOUT")
        .ok()
        .and_then(|s| s.parse::<String>().ok())
        .unwrap_or_else(|| "300".to_string());

    if let Some(parent) = runtime_file.parent() {
        fs::create_dir_all(parent).map_err(|error| {
            format!(
                "failed to create runtime metadata directory {}: {error}",
                parent.display()
            )
        })?;
    }

    let mut command = Command::new(&server_binary);
    command
        .arg("--port")
        .arg(port.to_string())
        .arg("--launcher-token")
        .arg(&token)
        .arg("--runtime-file")
        .arg(runtime_file)
        .arg("--idle-timeout-seconds")
        .arg(&idle_timeout)
        .arg("--no-kill-stale")
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());

    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = command.spawn().map_err(|error| {
        format!(
            "failed to start bundled ACE server {}: {error}",
            server_binary.display()
        )
    })?;

    let runtime = RuntimeInfo {
        pid: child.id(),
        port,
        token,
    };
    if let Err(error) = write_runtime_info(runtime_file, &runtime) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error);
    }
    Ok(LaunchedServer { runtime, child })
}

fn write_runtime_info(runtime_file: &Path, runtime: &RuntimeInfo) -> LauncherResult<()> {
    let bytes = serde_json::to_vec(runtime)
        .map_err(|error| format!("failed to encode runtime metadata: {error}"))?;
    fs::write(runtime_file, bytes).map_err(|error| {
        format!(
            "failed to write runtime metadata {}: {error}",
            runtime_file.display()
        )
    })
}

fn choose_port() -> LauncherResult<u16> {
    if port_is_available(PREFERRED_PORT) {
        return Ok(PREFERRED_PORT);
    }

    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| format!("failed to reserve a fallback server port: {error}"))?;
    let port = listener
        .local_addr()
        .map_err(|error| format!("failed to inspect fallback server port: {error}"))?
        .port();
    Ok(port)
}

fn port_is_available(port: u16) -> bool {
    TcpListener::bind(("127.0.0.1", port)).is_ok()
}

fn wait_for_runtime(runtime: &RuntimeInfo) -> LauncherResult<()> {
    let deadline = Instant::now() + STARTUP_TIMEOUT;
    while Instant::now() < deadline {
        if is_runtime_live(runtime) {
            return Ok(());
        }
        sleep(STATUS_POLL_INTERVAL);
    }
    Err(format!(
        "ACE server did not report ready on 127.0.0.1:{} before startup timeout",
        runtime.port
    ))
}

fn is_runtime_live(runtime: &RuntimeInfo) -> bool {
    if runtime.token.is_empty() {
        return false;
    }

    let url = format!(
        "http://127.0.0.1:{}/api/runtime/status",
        runtime.port
    );
    let request = ureq::get(&url)
        .header(LAUNCHER_TOKEN_HEADER, runtime.token.as_str())
        .config()
        .timeout_global(Some(STATUS_REQUEST_TIMEOUT))
        .build();

    let mut response = match request.call() {
        Ok(response) => response,
        Err(_) => return false,
    };

    response
        .body_mut()
        .with_config()
        .limit(2048)
        .read_json::<RuntimeStatus>()
        .map(|status| status.enabled && status.authenticated)
        .unwrap_or(false)
}

fn generate_token() -> String {
    let mut bytes = [0_u8; 32];
    rand::rng().fill_bytes(&mut bytes);
    hex_encode(&bytes)
}

fn hex_encode(bytes: &[u8]) -> String {
    const HEX: &[u8; 16] = b"0123456789abcdef";
    let mut output = String::with_capacity(bytes.len() * 2);
    for byte in bytes {
        output.push(HEX[(byte >> 4) as usize] as char);
        output.push(HEX[(byte & 0x0f) as usize] as char);
    }
    output
}

fn launch_url(port: u16, token: &str, open_path: Option<&Path>) -> String {
    let mut url = format!("http://127.0.0.1:{port}/launch?token={token}");
    if let Some(path) = open_path {
        url.push_str("&open=");
        url.push_str(&urlencoding::encode(&path.to_string_lossy()));
    }
    url
}

fn extract_ace_path_from_args<I, S>(args: I, current_dir: &Path) -> Option<PathBuf>
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    args.into_iter().find_map(|arg| {
        let path = parse_plain_or_file_url_path(arg.as_ref())?;
        if !has_ace_extension(&path) {
            return None;
        }
        Some(make_absolute(path, current_dir))
    })
}

fn parse_plain_or_file_url_path(value: &str) -> Option<PathBuf> {
    if value.starts_with("file://") {
        path_from_file_url(value)
    } else {
        Some(PathBuf::from(value))
    }
}

fn path_from_file_url(value: &str) -> Option<PathBuf> {
    let mut rest = value.strip_prefix("file://")?;
    if let Some(after_localhost) = rest.strip_prefix("localhost") {
        rest = after_localhost;
    }
    if rest.is_empty() {
        return None;
    }

    let decoded = urlencoding::decode(rest).ok()?;

    #[cfg(windows)]
    let path = {
        let mut path = decoded.into_owned();
        let bytes = path.as_bytes();
        if bytes.len() >= 3
            && bytes[0] == b'/'
            && bytes[1].is_ascii_alphabetic()
            && bytes[2] == b':'
        {
            path.remove(0);
        } else if !path.starts_with('/') && !path.starts_with('\\') {
            path.insert_str(0, "//");
        }
        path.replace('/', "\\")
    };

    #[cfg(not(windows))]
    let path = decoded.into_owned();

    Some(PathBuf::from(path))
}

fn has_ace_extension(path: &Path) -> bool {
    path.extension()
        .and_then(|extension| extension.to_str())
        .is_some_and(|extension| extension.eq_ignore_ascii_case("ace"))
}

fn make_absolute(path: PathBuf, current_dir: &Path) -> PathBuf {
    if path.is_absolute() {
        path
    } else {
        current_dir.join(path)
    }
}

fn add_server_candidates(candidates: &mut Vec<PathBuf>, root: &Path, server_name: &str) {
    #[cfg(target_os = "macos")]
    {
        candidates.push(
            root.join(format!("{server_name}.dist"))
                .join(server_name),
        );
    }
    candidates.push(root.join(server_name));
}

fn locate_server_binary() -> LauncherResult<PathBuf> {
    let server_name = server_binary_name();
    let exe = env::current_exe().map_err(|error| format!("failed to locate current executable: {error}"))?;
    let mut candidates = Vec::new();

    if let Some(exe_dir) = exe.parent() {
        if exe_dir.file_name().is_some_and(|name| name == OsStr::new("MacOS")) {
            if let Some(contents_dir) = exe_dir.parent() {
                add_server_candidates(&mut candidates, &contents_dir.join("Resources"), server_name);
            }
        }
        add_server_candidates(&mut candidates, exe_dir, server_name);
    }

    add_dev_fallback_candidates(&mut candidates, &exe, server_name);
    if let Ok(current_dir) = env::current_dir() {
        add_dev_fallback_candidates(&mut candidates, &current_dir, server_name);
    }

    candidates
        .iter()
        .find(|candidate| candidate.is_file())
        .cloned()
        .ok_or_else(|| {
            let searched = candidates
                .iter()
                .map(|candidate| format!("\n  - {}", candidate.display()))
                .collect::<String>();
            format!("missing bundled ACE server binary; searched:{searched}")
        })
}

fn add_dev_fallback_candidates(candidates: &mut Vec<PathBuf>, start: &Path, server_name: &str) {
    for ancestor in start.ancestors() {
        add_server_candidates(
            candidates,
            &ancestor
                .join("desktop")
                .join("launcher")
                .join("resources"),
            server_name,
        );
        if ancestor.file_name().is_some_and(|name| name == OsStr::new("desktop")) {
            add_server_candidates(
                candidates,
                &ancestor
                    .join("launcher")
                    .join("resources"),
                server_name,
            );
        }
    }
}

fn server_binary_name() -> &'static str {
    #[cfg(all(target_os = "macos", target_arch = "aarch64"))]
    {
        "ace-server-aarch64-apple-darwin"
    }
    #[cfg(all(target_os = "macos", target_arch = "x86_64"))]
    {
        "ace-server-x86_64-apple-darwin"
    }
    #[cfg(all(target_os = "windows", target_arch = "x86_64"))]
    {
        "ace-server-x86_64-pc-windows-msvc.exe"
    }
    #[cfg(all(target_os = "windows", target_arch = "aarch64"))]
    {
        "ace-server-aarch64-pc-windows-msvc.exe"
    }
    #[cfg(all(target_os = "linux", target_arch = "x86_64"))]
    {
        "ace-server-x86_64-unknown-linux-gnu"
    }
    #[cfg(not(any(
        all(target_os = "macos", target_arch = "aarch64"),
        all(target_os = "macos", target_arch = "x86_64"),
        all(target_os = "windows", target_arch = "x86_64"),
        all(target_os = "windows", target_arch = "aarch64"),
        all(target_os = "linux", target_arch = "x86_64")
    )))]
    {
        "ace-server"
    }
}

// ---------------------------------------------------------------------------
// macOS document-open capture
// ---------------------------------------------------------------------------

/// On macOS, Finder "Open With" delivers the file path via AppleEvents
/// rather than argv.  This module briefly starts an NSApplication delegate
/// to capture any pending `application:openFile:` event that arrived
/// during launch, then returns the path (if any) without entering the
/// full event loop.
#[cfg(target_os = "macos")]
mod macos_document_open {
    use std::cell::RefCell;
    use std::path::PathBuf;
    use std::time::{Duration, Instant};

    use objc2::rc::{autoreleasepool, Retained};
    use objc2::runtime::{NSObject, NSObjectProtocol, ProtocolObject};
    use objc2::{define_class, msg_send, DefinedClass, MainThreadMarker, MainThreadOnly};
    use objc2_app_kit::{NSApplication, NSApplicationDelegate};
    use objc2_foundation::NSString;

    // ---- delegate ---------------------------------------------------------

    struct LauncherDelegateIvars {
        captured_path: RefCell<Option<String>>,
    }

    impl Default for LauncherDelegateIvars {
        fn default() -> Self {
            Self {
                captured_path: RefCell::new(None),
            }
        }
    }

    define_class!(
        #[unsafe(super(NSObject))]
        #[thread_kind = MainThreadOnly]
        #[ivars = LauncherDelegateIvars]
        struct LauncherDelegate;

        unsafe impl NSObjectProtocol for LauncherDelegate {}

        unsafe impl NSApplicationDelegate for LauncherDelegate {
            #[unsafe(method(application:openFile:))]
            fn open_file(&self, _sender: &NSApplication, filename: &NSString) -> bool {
                *self.ivars().captured_path.borrow_mut() = Some(filename.to_string());
                true
            }
        }
    );

    impl LauncherDelegate {
        fn new(mtm: MainThreadMarker) -> Retained<Self> {
            let this = Self::alloc(mtm).set_ivars(LauncherDelegateIvars::default());
            unsafe { msg_send![super(this), init] }
        }
    }

    // ---- CoreFoundation run-loop FFI --------------------------------------

    extern "C" {
        /// `CFRunLoopRunInMode` – processes one iteration of the Core
        /// Foundation run loop.  Linked from the CoreFoundation framework,
        /// which is already a transitive dependency on macOS.
        fn CFRunLoopRunInMode(
            mode: *const std::ffi::c_void,
            seconds: f64,
            return_after_source_handled: u8,
        ) -> i32;

        static kCFRunLoopDefaultMode: *const std::ffi::c_void;
    }

    // ---- public entry point -----------------------------------------------

    /// Briefly polls for a macOS document-open AppleEvent (e.g. Finder
    /// "Open With" on a `.ace` file).  Returns `Some(path)` when an event
    /// was captured within `timeout`, `None` otherwise.  Never blocks
    /// longer than `timeout`.
    pub fn wait_for_document_open(timeout: Duration) -> Option<PathBuf> {
        let mtm = MainThreadMarker::new()?;

        let delegate = LauncherDelegate::new(mtm);
        autoreleasepool(|_| {
            let app = NSApplication::sharedApplication(mtm);
            app.setDelegate(Some(ProtocolObject::from_ref(&*delegate)));
        });

        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            autoreleasepool(|_| {
                // Process one run-loop source with a 50 ms ceiling.
                unsafe {
                    CFRunLoopRunInMode(kCFRunLoopDefaultMode, 0.05, 1);
                }
            });

            if delegate.ivars().captured_path.borrow().is_some() {
                break;
            }
        }

        let captured = delegate
            .ivars()
            .captured_path
            .borrow_mut()
            .take()
            .map(PathBuf::from);
        captured
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extracts_plain_ace_path_as_absolute_path() {
        let cwd = Path::new("/tmp/project");
        let path = extract_ace_path_from_args(["notes.txt", "data/example.ace"], cwd).unwrap();
        assert_eq!(path, cwd.join("data/example.ace"));
    }

    #[test]
    fn extracts_file_url_ace_path() {
        let cwd = Path::new("/tmp/project");
        let path = extract_ace_path_from_args(["file:///tmp/My%20Project/example.ace"], cwd).unwrap();
        assert_eq!(path, PathBuf::from("/tmp/My Project/example.ace"));
    }

    #[test]
    fn ignores_non_ace_paths() {
        let cwd = Path::new("/tmp/project");
        assert!(extract_ace_path_from_args(["file:///tmp/example.txt", "--flag"], cwd).is_none());
    }

    #[test]
    fn builds_launch_url_without_open_path() {
        assert_eq!(
            launch_url(18080, "abc123", None),
            "http://127.0.0.1:18080/launch?token=abc123"
        );
    }

    #[test]
    fn builds_launch_url_with_encoded_open_path() {
        let url = launch_url(18081, "abc123", Some(Path::new("/tmp/My Project/demo.ace")));
        assert_eq!(
            url,
            "http://127.0.0.1:18081/launch?token=abc123&open=%2Ftmp%2FMy%20Project%2Fdemo.ace"
        );
    }

    #[test]
    fn hex_encoding_uses_two_lowercase_digits_per_byte() {
        assert_eq!(hex_encode(&[0, 1, 15, 16, 255]), "00010f10ff");
    }
}
