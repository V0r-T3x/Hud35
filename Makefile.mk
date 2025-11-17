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
DEPS := git python3-pip python3-evdev python3-numpy python3-pil python3-flask python3-toml fonts-dejavu-core python3-rpi.gpio

# Optional dependencies for Waveshare E-Paper displays
WAVESHARE_DEPS := libjpeg-dev zlib1g-dev libpng-dev libfreetype6-dev liblcms2-dev libwebp-dev libtiff-dev libopenjp2-7-dev libxcb1-dev

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
	@echo "   Run 'make configure' to configure api keys and setup display."

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
	@echo "---> Copying configuration helper script..."
	sudo cp set_config.py $(APP_DIR)/
	@echo "---> Setting application file permissions..."
	sudo chown -R $(APP_USER):$(APP_USER) $(APP_DIR)
	@echo "---> Creating Python virtual environment at $(VENV_DIR)..."
	sudo -u $(APP_USER) $(PYTHON_EXECUTABLE) -m venv --system-site-packages $(VENV_DIR)
	@echo "---> Installing Python dependencies into virtual environment..."
	sudo -u $(APP_USER) $(VENV_DIR)/bin/pip install --upgrade pip
	sudo -u $(APP_USER) $(VENV_DIR)/bin/pip install -r $(APP_DIR)/requirements.txt

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

##@ Configuration

configure: ## Run an interactive wizard to configure API keys and display.
	$(eval SHELL:=/bin/bash)
	@echo "--- Starting Hud35 Interactive Setup Wizard ---"
	@echo "This will guide you through setting up API keys and your display."
	@echo "Press [Enter] to skip any setting."
	@echo ""
	@# --- API Key Configuration ---
	@read -p "Enter your OpenWeatherMap API Key: " OWM_API_KEY; \
	if [ -n "$$OWM_API_KEY" ]; then \
		echo "---> Setting OpenWeatherMap API Key..."; \
		sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml api_keys openweather "$$OWM_API_KEY"; \
	fi
	@read -p "Enter your Google Geolocation API Key: " GOOGLE_API_KEY; \
	if [ -n "$$GOOGLE_API_KEY" ]; then \
		echo "---> Setting Google Geolocation API Key..."; \
		sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml api_keys google_geo "$$GOOGLE_API_KEY"; \
	fi
	@read -p "Enter your Spotify Client ID: " SPOTIFY_CLIENT_ID; \
	if [ -n "$$SPOTIFY_CLIENT_ID" ]; then \
		echo "---> Setting Spotify Client ID..."; \
		sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml api_keys client_id "$$SPOTIFY_CLIENT_ID"; \
	fi
	@read -p "Enter your Spotify Client Secret: " SPOTIFY_CLIENT_SECRET; \
	if [ -n "$$SPOTIFY_CLIENT_SECRET" ]; then \
		echo "---> Setting Spotify Client Secret..."; \
		sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml api_keys client_secret "$$SPOTIFY_CLIENT_SECRET"; \
	fi
	@echo ""
	@# --- Display Configuration ---
	@echo "Select your display type:"
	@echo "  1) Display HAT Mini (st7789)"
	@echo "  2) 3.5\" TFT Framebuffer (e.g., ILI9486)"
	@echo "  3) Waveshare E-Paper Display"
	@read -p "Enter the number for your display [1-3]: " DISPLAY_CHOICE; \
	if [[ "$$DISPLAY_CHOICE" =~ ^[1-3]$$ ]]; then \
		read -p "Enter screen rotation (0, 180) [default: 0]: " ROTATION; \
		ROTATION=$${ROTATION:-0}; \
		if [[ "$$ROTATION" =~ ^(0|180)$$ ]]; then \
			echo "---> Setting screen rotation to $$ROTATION..."; \
			sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display rotation "$$ROTATION"; \
		else \
			echo "⚠️ Invalid rotation value '$$ROTATION'. Skipping rotation setup."; \
		fi; \
		echo ""; \
		case $$DISPLAY_CHOICE in \
			1) echo "Selected Display HAT Mini. Installing..."; $(MAKE) install-st7789 ;; \
			2) \
				echo "Selected 3.5\" TFT Framebuffer. Installing..."; \
				read -p "Enter framebuffer device number (0 or 1) [default: 1]: " FB_NUM; \
				FB_NUM=$${FB_NUM:-1}; \
				sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display framebuffer "/dev/fb$$FB_NUM"; \
				$(MAKE) install-framebuffer-3.5; \
				;; \
			3) echo "Selected Waveshare E-Paper. Installing..."; $(MAKE) install-waveshare-epd ;; \
		esac; \
	else \
		echo "Invalid selection. Skipping display setup."; \
	fi;
	@echo "\n✅ Interactive configuration complete."
	@echo "   Spotify authentication must be completed via the web interface."

install-framebuffer-3.5: ## Install drivers for 3.5" TFT (framebuffer) displays.
	@echo "---> Installing drivers for 3.5 inch TFT display as per README.md..."
	rm -rf LCD-show
	git clone https://github.com/Shinigamy19/RaspberryPi3bplus-3.5inch-displayA-ILI9486-MPI3501-XPT2046
	mv RaspberryPi3bplus-3.5inch-displayA-ILI9486-MPI3501-XPT2046 LCD-show
	cd LCD-show && chmod +x LCD35-show && sudo ./LCD35-show
	@echo "---> Configuring screen type to 'framebuffer' in config.toml..."
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display width 480
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display height 320
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display type framebuffer
	@echo "✅ 3.5 inch TFT driver installation script executed."
	@echo "   A reboot is required to activate the display driver."

install-waveshare-epd: ## Install Python driver for Waveshare E-Paper displays.
	@echo "---> Installing system libraries for Waveshare E-Paper (Pillow dependencies)..."
	sudo apt-get install -y $(WAVESHARE_DEPS)
	@echo "---> Installing eink-wave driver into virtual environment..."
	sudo -u $(APP_USER) $(VENV_DIR)/bin/pip install eink-wave
	@echo "---> Configuring screen type to 'waveshare_epd' in config.toml..."
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display type waveshare_epd
	@echo "✅ Waveshare E-Paper driver installed."

##@ Display Drivers

install-st7789: ## Install Python driver for ST7789 displays (Display HAT Mini).
	@echo "---> Installing ST7789 driver into virtual environment..."
	sudo -u $(APP_USER) $(VENV_DIR)/bin/pip install st7789
	@echo "---> Configuring screen type to 'st7789' in config.toml..."
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display type st7789
	@echo "---> Setting default configuration for [display.st7789]..."
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display.st7789 spi_port 0
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display.st7789 spi_cs 1
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display.st7789 dc_pin 9
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display.st7789 backlight_pin 13
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display.st7789 rotation 0
	sudo -u $(APP_USER) $(VENV_DIR)/bin/python3 $(APP_DIR)/set_config.py $(APP_DIR)/config.toml display.st7789 spi_speed 60000000
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