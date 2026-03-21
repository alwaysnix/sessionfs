class Sessionfs < Formula
  include Language::Python::Virtualenv

  desc "Sync daemon for AI agent sessions"
  homepage "https://sessionfs.dev"
  url "https://files.pythonhosted.org/packages/source/s/sessionfs/sessionfs-0.1.0.tar.gz"
  sha256 "TODO_REPLACE_WITH_ACTUAL_SHA256"
  license "Apache-2.0"

  depends_on "python@3.12"

  def install
    virtualenv_install_with_resources
  end

  service do
    run [opt_bin/"sfsd"]
    keep_alive true
    log_path var/"log/sessionfs.log"
    error_log_path var/"log/sessionfs-error.log"
  end

  test do
    system "#{bin}/sfs", "--help"
    system "#{bin}/sfs", "list"
  end
end
