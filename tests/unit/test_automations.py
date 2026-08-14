"""Unit tests for Home Assistant automation discovery and reference extraction."""

from app.collectors.automations import (
    collect_automation_models,
    collect_automations,
    parse_automation_dict,
)
from app.exporters.json_exporter import build_entity_usage_map
from app.models.entity import EntityModel


def test_parse_automation_dict_basic_and_triggers_actions():
    raw_auto = {
        "id": "12345",
        "alias": "Living Room Motion Light",
        "description": "Turn on light when motion detected",
        "mode": "single",
        "trigger": [
            {
                "trigger": "state",
                "entity_id": "binary_sensor.living_room_motion",
                "to": "on",
            },
            {
                "trigger": "numeric_state",
                "entity_id": "sensor.living_room_illuminance",
                "below": 50,
            },
        ],
        "condition": [
            {
                "condition": "state",
                "entity_id": "input_boolean.guest_mode",
                "state": "off",
            }
        ],
        "action": [
            {
                "service": "light.turn_on",
                "target": {
                    "entity_id": "light.living_room",
                    "device_id": "dev_living_room_light",
                    "area_id": "living_room_area",
                },
            },
            {
                "service": "script.notify_motion",
            },
            {
                "service": "scene.living_room_bright",
            },
            {
                "service": "automation.trigger",
                "target": {"entity_id": "automation.secondary_alert"},
            },
        ],
    }

    model = parse_automation_dict(raw_auto, source_file="automations.yaml")

    assert model.id == "12345"
    assert model.alias == "Living Room Motion Light"
    assert model.source_file == "automations.yaml"
    assert model.mode == "single"
    assert len(model.triggers) == 2
    assert "binary_sensor.living_room_motion" in model.triggers[0]
    assert len(model.conditions) == 1
    assert "input_boolean.guest_mode" in model.conditions[0]
    assert len(model.actions) == 4
    assert "light.turn_on" in model.called_services
    assert "script.notify_motion" in model.called_scripts
    assert "scene.living_room_bright" in model.called_scenes
    assert (
        "automation.secondary_alert" in model.entities
        or "automation.trigger" in model.called_automations
    )

    assert "binary_sensor.living_room_motion" in model.entities
    assert "sensor.living_room_illuminance" in model.entities
    assert "light.living_room" in model.entities
    assert "input_boolean.guest_mode" in model.helpers
    assert "dev_living_room_light" in model.devices
    assert "living_room_area" in model.areas


def test_parse_automation_dict_complex_structures_and_jinja():
    raw_auto = {
        "alias": "Complex Security Automation",
        "trigger": {"platform": "time", "at": "22:00:00"},
        "condition": [
            {
                "condition": "template",
                "value_template": (
                    "{{ is_state('input_boolean.security_armed', 'on')"
                    " and state_attr('climate.house', 'temperature') > 20 }}"
                ),
            }
        ],
        "action": [
            {
                "choose": [
                    {
                        "conditions": [
                            {
                                "condition": "template",
                                "value_template": (
                                    "{{ states.sensor.door_lock.state == 'unlocked' }}"
                                ),
                            }
                        ],
                        "sequence": [
                            {
                                "service": "lock.lock",
                                "target": {"entity_id": "lock.front_door"},
                            }
                        ],
                    }
                ],
                "default": [
                    {
                        "repeat": {
                            "count": 2,
                            "sequence": [
                                {
                                    "service": "notify.mobile_app",
                                    "data": {
                                        "message": (
                                            "Security check {{ states('sensor.pool_temperature') }}"
                                        )
                                    },
                                }
                            ],
                        }
                    }
                ],
            },
            {
                "service": "script.turn_on",
                "target": {"entity_id": "script.alarm_flash"},
            },
            {
                "wait_for_trigger": [
                    {
                        "platform": "state",
                        "entity_id": "binary_sensor.front_door_contact",
                        "to": "off",
                    }
                ]
            },
        ],
    }

    model = parse_automation_dict(raw_auto, source_file="packages/security.yaml")

    assert "input_boolean.security_armed" in model.entities
    assert "input_boolean.security_armed" in model.helpers
    assert "climate.house" in model.entities
    assert "sensor.door_lock" in model.entities
    assert "lock.front_door" in model.entities
    assert "sensor.pool_temperature" in model.entities
    assert "binary_sensor.front_door_contact" in model.entities
    assert "lock.lock" in model.called_services
    assert "notify.mobile_app" in model.called_services
    assert "script.alarm_flash" in model.called_scripts or "script.alarm_flash" in model.entities


def test_collect_automations_discovery_across_files(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # 1. automations.yaml
    auto_yaml = config_dir / "automations.yaml"
    auto_yaml.write_text(
        """
- id: 'auto_1'
  alias: 'Auto 1'
  trigger:
    - platform: state
      entity_id: light.living_room
      to: 'on'
  action:
    - service: switch.turn_on
      target:
        entity_id: switch.plug_1
""",
        encoding="utf-8",
    )

    # 2. packages/alarm.yaml
    pkg_dir = config_dir / "packages"
    pkg_dir.mkdir()
    (pkg_dir / "alarm.yaml").write_text(
        """
automation:
  - id: 'auto_pkg'
    alias: 'Package Alarm Auto'
    trigger:
      - platform: state
        entity_id: binary_sensor.alarm_motion
        to: 'on'
    action:
      - service: alarm_control_panel.alarm_arm_home
        target:
          entity_id: alarm_control_panel.home_alarm
""",
        encoding="utf-8",
    )

    models, _warnings = collect_automation_models(config_dir)

    assert len(models) == 2
    aliases = {m.alias for m in models}
    assert "Auto 1" in aliases
    assert "Package Alarm Auto" in aliases

    auto_map, _ = collect_automations(config_dir)
    assert "Auto 1" in auto_map
    assert "Package Alarm Auto" in auto_map
    assert "light.living_room" in auto_map["Auto 1"]
    assert "switch.plug_1" in auto_map["Auto 1"]


def test_build_entity_usage_map():
    auto_model = parse_automation_dict(
        {
            "id": "auto_guest",
            "alias": "Guest Mode Auto",
            "condition": [
                {
                    "condition": "state",
                    "entity_id": "input_boolean.guest_mode",
                    "state": "on",
                }
            ],
            "action": [
                {
                    "service": "input_boolean.turn_off",
                    "target": {"entity_id": "input_boolean.guest_mode"},
                }
            ],
        }
    )

    entities = [EntityModel(entity_id="input_boolean.guest_mode", name="Guest Mode")]

    usage_map = build_entity_usage_map(
        automation_models=[auto_model],
        scripts_detailed=[],
        dashboards=[],
        entities=entities,
    )

    assert "input_boolean.guest_mode" in usage_map
    guest_usage = usage_map["input_boolean.guest_mode"]
    assert len(guest_usage["automations"]) == 1
    assert guest_usage["automations"][0]["id"] == "auto_guest"
    assert "condition" in guest_usage["automations"][0]["usage"]
    assert "action" in guest_usage["automations"][0]["usage"]


def test_collect_automations_includes_and_dir_merges(tmp_path):
    config_dir = tmp_path / "config"
    config_dir.mkdir()

    # 1. automations.yaml
    (config_dir / "automations.yaml").write_text(
        """
- id: 'inc_auto_1'
  alias: 'Included Auto'
  trigger:
    - platform: device
      device_id: dev_motion_1
      domain: binary_sensor
      type: motion
  condition:
    - condition: state
      entity_id:
        - input_boolean.night_mode
        - input_boolean.vacation_mode
      state: 'on'
  action:
    - service: light.turn_on
      target:
        device_id: dev_light_1
        area_id: hallway
""",
        encoding="utf-8",
    )

    # 2. Subdirectory automation file (e.g. automations/cooling.yaml)
    inc_dir = config_dir / "automations"
    inc_dir.mkdir()
    (inc_dir / "cooling.yaml").write_text(
        """
id: 'dir_auto_1'
alias: 'Dir Listed Auto'
trigger:
  - platform: numeric_state
    entity_id: sensor.temp
    above: 25
    below: 30
action:
  - repeat:
      while:
        - condition: state
          entity_id: input_boolean.fan_running
          state: 'off'
      sequence:
        - service: fan.turn_on
          target:
            entity_id: fan.ceiling_fan
""",
        encoding="utf-8",
    )

    # 3. configuration.yaml referencing automations and split configurations
    (config_dir / "configuration.yaml").write_text(
        """
automation split:
  id_keyed_auto_1:
    alias: 'ID Keyed Auto'
    trigger:
      - platform: event
        event_type: custom_button_click
        event_data:
          entity_id: event.remote_button
    action:
      - parallel:
          - service: counter.increment
            target:
              entity_id: counter.click_counter
          - service: timer.start
            target:
              entity_id: timer.motion_timer
          - service: schedule.reload
            target:
              entity_id: schedule.heating
          - wait_template: "{{ is_state('input_button.reset', 'on') }}"
""",
        encoding="utf-8",
    )

    models, _warnings = collect_automation_models(config_dir)

    aliases = {m.alias: m for m in models}
    assert "Included Auto" in aliases
    assert "Dir Listed Auto" in aliases
    assert "ID Keyed Auto" in aliases

    inc_auto = aliases["Included Auto"]
    assert "dev_motion_1" in inc_auto.devices
    assert "input_boolean.night_mode" in inc_auto.entities
    assert "input_boolean.vacation_mode" in inc_auto.entities
    assert "hallway" in inc_auto.areas

    dir_auto = aliases["Dir Listed Auto"]
    assert "sensor.temp" in dir_auto.entities
    assert "input_boolean.fan_running" in dir_auto.entities
    assert "fan.ceiling_fan" in dir_auto.entities
    assert "fan.turn_on" in dir_auto.called_services

    id_auto = aliases["ID Keyed Auto"]
    assert "counter.click_counter" in id_auto.helpers
    assert "timer.motion_timer" in id_auto.helpers
    assert "schedule.heating" in id_auto.helpers
    assert "input_button.reset" in id_auto.entities
    assert "custom_button_click" in id_auto.triggers[0]
