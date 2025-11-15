# Makefile for Hud35 Application

# --- Configuration ---
# These variables can be overridden from the command line.
# e.g., make install APP_USER=myuser

# Project and User Settings
PROJECT_NAME := hud35
APP_USER ?= pi

# Directory Settings
APP_DIR ?= /opt/$(PROJECT_NAME)
VENV_DIR ?= $(APP_DIR)/venv
LOG_DIR ?= /var/log/$(PROJECT_NAME)
CONFIG_DIR ?= /etc/$(PROJECT_NAME)

# Python Settings
PYTHON_EXECUTABLE ?= python3

# System dependencies from README.md and install.sh
DEPS := git python3-pip python3-evdev python3-numpy python3-pil python3-flask python3-toml fonts-dejavu-core

# Use .DEFAULT_GOAL to make `help` the default action.
.DEFAULT_GOAL := help

# Phony targets don't represent files.
.PHONY: all install uninstall clean reinstall help \
		install-deps setup-spi setup-user setup-dirs setup-app setup-service \
		uninstall-service uninstall-app

##@ General

all: install ## Install the application, and all dependencies.

reinstall: uninstall install ## Uninstall and then reinstall the application.

clean: ## Remove local build artifacts and __pycache__ directories.
	@echo "Cleaning up local build artifacts..."
	find . -type f -name "*.pyc" -delete
	find . -type d -name "__pycache__" -delete
	rm -rf .venv build dist *.egg-info

##@ Installation

install: install-deps setup-spi setup-user setup-dirs setup-app setup-service ## Run the full installation process.
	@echo "\n✅ Hud35 installation complete."
	@echo "   Service '$(PROJECT_NAME).service' is enabled and started."
	@echo "\n   🚨 IMPORTANT: A system reboot is required for hardware permissions to take effect."
	@echo "   Run 'make status' to check the application status."

install-deps:
	@echo "---> Updating package lists and installing system dependencies..."
	sudo apt-get update
	sudo apt-get install -y $(DEPS)

setup-spi:
	@echo "---> Enabling SPI interface via raspi-config..."
	sudo raspi-config nonint do_spi 0
	@echo "✅ SPI enabled. A reboot is recommended to ensure all hardware changes take effect."

setup-user:
	@echo "---> Ensuring user '$(APP_USER)' exists..."
	-sudo id -u $(APP_USER) >/dev/null 2>&1 || { echo "User $(APP_USER) not found. Please create it or specify an existing user with 'make install APP_USER=<username>'."; exit 1; }
	@echo "---> Adding user '$(APP_USER)' to 'video' and 'gpio' groups for hardware access..."
	sudo usermod -a -G video,gpio $(APP_USER)
	@echo "✅ User permissions updated. A reboot is required for these changes to apply."

setup-dirs:
	@echo "---> Creating application directories..."
	sudo mkdir -p $(APP_DIR)
	sudo mkdir -p $(APP_DIR)/templates
	sudo mkdir -p $(LOG_DIR)
	@echo "---> Setting permissions..."
	sudo chown -R $(APP_USER):$(APP_USER) $(APP_DIR)
	sudo chown -R $(APP_USER):$(APP_USER) $(APP_DIR)/templates
	sudo chown -R $(APP_USER):$(APP_USER) $(LOG_DIR)

setup-app:
	@echo "---> Copying application files to $(APP_DIR)..."
	sudo rsync -a --delete --exclude='.git' --exclude='*.pyc' --exclude='__pycache__' --exclude='.venv' --exclude='Makefile.mk' ./ $(APP_DIR)/
	@echo "---> Setting application file permissions..."
	sudo chown -R $(APP_USER):$(APP_USER) $(APP_DIR)
	@echo "---> Creating Python virtual environment at $(VENV_DIR)..."
	sudo -u $(APP_USER) $(PYTHON_EXECUTABLE) -m venv $(VENV_DIR)
	@echo "---> Installing Python dependencies from requirements.txt..."
	sudo $(VENV_DIR)/bin/pip install --upgrade pip
	sudo $(VENV_DIR)/bin/pip install -r $(APP_DIR)/requirements.txt

setup-service:
	@echo "---> Creating and enabling systemd service for Hud35..."
	@echo "[Unit]" | sudo tee /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "Description=Hud35 Launcher Service" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "After=network.target" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "[Service]" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "User=$(APP_USER)" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "Group=$(APP_USER)" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "WorkingDirectory=$(APP_DIR)" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "ExecStart=$(VENV_DIR)/bin/python3 $(APP_DIR)/launcher.py" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "Restart=always" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "StandardOutput=journal" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "StandardError=journal" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "[Install]" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	@echo "WantedBy=multi-user.target" | sudo tee -a /etc/systemd/system/$(PROJECT_NAME).service > /dev/null
	sudo systemctl daemon-reload
	sudo systemctl enable --now $(PROJECT_NAME).service

##@ Uninstallation

uninstall: uninstall-service uninstall-app ## Uninstall the application and its services.
	@echo "\n✅ Hud35 uninstallation complete."

uninstall-service:
	@echo "---> Stopping and removing systemd service..."
	-sudo systemctl stop $(PROJECT_NAME).service
	-sudo systemctl disable $(PROJECT_NAME).service
	-sudo rm -f /etc/systemd/system/$(PROJECT_NAME).service
	-sudo systemctl daemon-reload

uninstall-app:
	@echo "---> Removing application files and directories..."
	-sudo rm -rf $(APP_DIR)
	-sudo rm -rf $(LOG_DIR)

##@ Display Drivers

install-st7789: ## Install Python driver for ST7789 displays (Display HAT Mini).
	@echo "---> Installing ST7789 driver into virtual environment..."
	sudo $(VENV_DIR)/bin/pip install st7789
	@echo "✅ ST7789 driver installed."

##@ Service Management

start: ## Start the hud35 systemd service.
	sudo systemctl start $(PROJECT_NAME).service

stop: ## Stop the hud35 systemd service.
	sudo systemctl stop $(PROJECT_NAME).service

restart: ## Restart the hud35 systemd service.
	sudo systemctl restart $(PROJECT_NAME).service

status: ## Check the status of the hud3s systemd service.
	sudo systemctl status $(PROJECT_NAME).service

logs: ## Tail the logs for the hud35 launcher service.
	sudo journalctl -u $(PROJECT_NAME).service -f

##@ Help

help: ## Show this help message.
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'