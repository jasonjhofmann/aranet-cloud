# Aranet Cloud API — full enumeration

openapi: 3.0.3
title:   Aranet Cloud API
version: 1.0

## Security schemes
  ApiKey: {'in': 'header', 'name': 'ApiKey', 'type': 'apiKey'}

## Components / schemas
  total: 48
  common.BaseResponse: object [error:array, links:object]
  common.Dictionary: object  (<no desc>)
  common.ErrorDesc: object [details:array, id:string, message:string]
  common.ErrorDetails: object [action:string, id:string, name:string, type:string]
  common.FKNamedObj: object [id:string, name:string]
  common.FKObj: object [id:string]
  common.Link: object [args:common.Dictionary, href:string, id:string, name:string]
  common.LinkDesc: object [href:string, name:string, rel:string]
  sensor.AlarmInfo: object [alarmed:string, id:string, metric:string, note:string, resolved:string, rule:string, sensor:string, severity:integer, threshold:string, unit:string, value:number, worst:number]
  sensor.AlarmRuleInfo: object [created:string, id:string, metric:string, name:string, notes:string]
  sensor.AlarmRuleListResponse: object [error:array, links:object, rules:array]
  sensor.AlarmsListResponse: object [alarms:array, error:array, links:object, self:string]
  sensor.AssetDesc: object [files:array, id:string, location:string, name:string, notes:string, points:array, tags:array]
  sensor.AssetSensorDesc: object [id:string, placed:string, probe:integer, removed:string, sensor:string]
  sensor.Assets: object [assets:array, error:array, links:object]
  sensor.MeasurementPointDesc: object [associations:array, id:string, name:string, skills:array]
  sensor.MeasurementPointSkillDesc: object [active:boolean, metric:string]
  sensor.MetricInfo: object [icon:string, id:string, kind:string, name:string, sensors:integer, units:array]
  sensor.MetricListResponse: object [error:array, links:object, metrics:array]
  sensor.MetricResponse: object [error:array, links:object, metric:sensor.MetricInfo]
  sensor.PairingDesc: object [base:string, paired:string, removed:string]
  sensor.ProbeDesc: object [color:string, label:string, name:string, probe:integer]
  sensor.ProbeNrDesc: object [probe:integer]
  sensor.ReadingDesc: object [asset:common.Link, metric:string, novelty:string, point:common.Link, probe:integer, sensor:string, time:string, unit:string, value:number]
  sensor.ReadingsListResponse: object [error:array, links:object, next:string, readings:array, self:string]
  sensor.SensorDesc: object [bases:array, files:array, id:string, name:string, pairing:array, probes:array, sensorId:string, skills:array, tags:array, type:string]
  sensor.SensorListResponse: object [error:array, links:object, sensors:array]
  sensor.SensorTypeDescr: object [conversionType:common.FKObj, icon:string, id:string, isVirtual:boolean, name:string]
  sensor.SensorTypeListResponse: object [error:array, links:object, sensorTypes:array]
  sensor.SensorTypeResponse: object [error:array, links:object, sensorType:sensor.SensorTypeDescr]
  sensor.SkillDesc: object [active:boolean, metric:string, probes:array]
  sensor.UnitInfo: object [default:boolean, id:string, name:string, precision:integer, selected:boolean]
  tags.TagDesc: object [id:string, name:string, notes:string, type:tags.TagType]
  tags.TagListResponse: object [error:array, links:object, tags:array]
  tags.TagResponse: object [error:array, links:object, tag:tags.TagDesc]
  tags.TagType: object [color:?, icon:?, id:string, name:string]
  tenant.BaseInfo: object [baseSensors:?, board:string, config:tenant.ConfigDesc, firmware:string, id:string, lastSeen:string, name:string, pausedate:string, product:string, regdate:string, region:string, self:string, sensors:string, tags:array, upgrade:string]
  tenant.BaseListResponse: object [bases:array, error:array, links:object]
  tenant.BaseResponse: object [base:tenant.BaseInfo, error:array, links:object]
  tenant.ConfigDesc: object [bacnet:tenant.bacnetDesc, ethernet:tenant.ethernetDesc, gsm:tenant.enabledDesc, lte:tenant.lteDesc, modbus:tenant.modbusDesc, modified:string, mqtt:tenant.mqttDesc, ntp:tenant.ntpDesc, snmp:tenant.enabledDesc, wifi:tenant.wifiDesc]
  tenant.bacnetDesc: object [deviceID:string, enabled:boolean, location:string, networkID:string, objType:common.FKNamedObj, port:integer]
  tenant.enabledDesc: object [enabled:boolean]
  tenant.ethernetDesc: object [dns:string, fallback:boolean, gateway:string, ipaddr:string, ipconfig:common.FKNamedObj, netmask:string]
  tenant.lteDesc: object [apn:string, enabled:boolean]
  tenant.modbusDesc: object [addresses:common.FKNamedObj, enabled:boolean, port:integer]
  tenant.mqttDesc: object [authenticated:boolean, enabled:boolean, encryption:common.FKNamedObj, format:common.FKNamedObj, host:string, port:integer, protocol:common.FKNamedObj, qos:string, rootTopic:string, user:string]
  tenant.ntpDesc: object [enabled:boolean, servers:array]
  tenant.wifiDesc: object [channel:integer, country:string, dns:string, enabled:boolean, encryption:common.FKNamedObj, gateway:string, ipaddr:string, ipconfig:common.FKNamedObj, mode:common.FKNamedObj, netmask:string, ssid:string, txpower:integer]

## Endpoints (full detail)

### GET /api/v1/alarms/actual
  summary: Actual alarms
  200 application/json: ref → sensor.AlarmsListResponse
  400 application/json: ref → common.BaseResponse
  500 application/json: ref → common.BaseResponse

### GET /api/v1/alarms/history
  summary: Historical alarms
  parameters:
    query  from                     : string (date-time)  — Time period from
    query  to                       : string (date-time)  — Time period to
  200 application/json: ref → sensor.AlarmsListResponse
  400 application/json: ref → common.BaseResponse
  500 application/json: ref → common.BaseResponse

### GET /api/v1/alarms/rules
  summary: Alarm rules
  200 application/json: ref → sensor.AlarmRuleListResponse
  400 application/json: ref → common.BaseResponse
  500 application/json: ref → common.BaseResponse

### GET /api/v1/alarms/rules/rule/{rule}
  summary: Alarms.Api.RulesRead
  parameters:
    path   rule                     *: integer (int32)  — Alarm rule id
  200: (no body)

### GET /api/v1/assets
  summary: Assets
  200 application/json: ref → sensor.Assets

### GET /api/v1/assets/asset/{asset}
  summary: Assets.Api.Read
  parameters:
    path   asset                    *: integer (int32)  — Asset id
  200: (no body)

### GET /api/v1/assets/asset/{asset}/attachment/{attid}
  summary: Attachment.Api.Asset.Attachment.Info
  parameters:
    path   asset                    *: integer (int32)  — Asset id
    path   attid                    *: string  — 
  200: (no body)

### GET /api/v1/assets/asset/{asset}/attachment/{attid}/file
  summary: Attachment.Api.Asset.Attachment.Data
  parameters:
    path   asset                    *: integer (int32)  — Asset id
    path   attid                    *: string  — 
  200: (no body)

### GET /api/v1/assets/asset/{asset}/attachment/{attid}/thumbnail
  summary: Attachment.Api.Asset.Attachment.Thumbnail
  parameters:
    path   asset                    *: integer (int32)  — Asset id
    path   attid                    *: string  — 
  200: (no body)

### GET /api/v1/bases
  summary: List of all base stations registered into Cloud.
  200 application/json: ref → tenant.BaseListResponse

### GET /api/v1/bases/base/{base}
  summary: Metadata of one base station.
  parameters:
    path   base                     *: string  — Base station ID
  200 application/json: ref → tenant.BaseResponse

### GET /api/v1/measurements/history
  summary: Sensor and asset measurement history
  description: Sensor and asset measurements for a specific period. If parameters are not selected, the endpoint returns the last 24-hour measurements for all sensors and assets and the maximum period available is 7
  parameters:
    query  sensor                   : string  — Comma-separated sensor IDs. If the parameter is set, then the default period is 7 days and the maximum period available is 6 months.
    query  asset                    : string  — Comma-separated asset IDs. If the parameter is set, then the default period is last 24-hours and the maximum period available is 6 months.
    query  point                    : string  — Comma-separated point IDs. If the parameter is set, then the default period is last 24-hours and the maximum period available is 6 months.
    query  metric                   : string  — Comma-separated metric IDs. If the parameter is set, the endpoint returns measurements for the selected metric only.
    query  unit                     : string  — Comma separated list of unit IDs. Not valid for application/senml+json format.
    query  from                     : string (date-time)  — UTC date for the start of the period. Date format: YYYY-MM-DD (HH:MM optional)
    query  to                       : string (date-time)  — UTC date for the end of the period. Date format: YYYY-MM-DD (HH:MM optional).
    query  seconds                  : integer  — Query measurements for the last n seconds.
    query  minutes                  : integer  — Query measurements for the last n minutes.
    query  hours                    : integer  — Query measurements for the last n hours.
    query  days                     : integer  — Query measurements for the last n days (including the current day). The start of the day is defined by the UTC time zone
    query  next                     : string  — Next page token. Use a link from ReadingsListResponse.next or NextLink response header. Due to optimization, the last page can be empty.
    query  limit                    : string  — Rows per page. Due to optimization, the page size can be less than the set limit.
    query  links                    : boolean  — Include links to the related resources. Enabled by default.
  200 application/json: ref → sensor.ReadingsListResponse
  200 application/senml+json: ref → sensor.ReadingsListResponse

### GET /api/v1/measurements/last
  summary: Last measurements
  description: Last recorded measurement for each individual sensor and asset. By default all sensors and assets are selected.
  parameters:
    query  sensor                   : string  — Comma-separated sensor IDs.
    query  asset                    : string  — Comma-separated asset IDs.
    query  point                    : string  — Comma-separated point IDs.
    query  metric                   : string  — Coma separated metric IDs.
    query  unit                     : string  — Comma-separated list of unit IDs. Not valid for application/senml+json format.
    query  links                    : boolean  — Include links to the related resources. Enabled by default.
  200 application/json: ref → sensor.ReadingsListResponse
  200 application/senml+json: ref → sensor.ReadingsListResponse

### GET /api/v1/metrics
  summary: List of available metrics
  200 application/json: ref → sensor.MetricListResponse
  400 application/json: ref → common.BaseResponse
  500 application/json: ref → common.BaseResponse

### GET /api/v1/metrics/{metric}
  summary: Metric data
  parameters:
    path   metric                   *: integer (int32)  — Metric id
  200 application/json: ref → sensor.MetricResponse
  400 application/json: ref → common.BaseResponse
  500 application/json: ref → common.BaseResponse

### GET /api/v1/sensors
  summary: Metadata of all the sensors.
  parameters:
    query  base                     : string  — Comma separated base station IDs to be used as filter. Sensors from all base stations will be included by default.
  200 application/json: ref → sensor.SensorListResponse
  400 application/json: ref → common.BaseResponse
  500 application/json: ref → common.BaseResponse

### GET /api/v1/sensors/sensor/{sensor}
  summary: Sensors.Api.Read
  parameters:
    path   sensor                   *: integer (int32)  — Sensor id
  200: (no body)

### GET /api/v1/sensors/sensor/{sensor}/attachment/{attid}
  summary: Attachment.Api.Attachment.Info
  parameters:
    path   sensor                   *: integer (int32)  — Sensor id
    path   attid                    *: string  — 
  200: (no body)

### GET /api/v1/sensors/sensor/{sensor}/attachment/{attid}/file
  summary: Attachment.Api.Attachment.Data
  parameters:
    path   sensor                   *: integer (int32)  — Sensor id
    path   attid                    *: string  — 
  200: (no body)

### GET /api/v1/sensors/sensor/{sensor}/attachment/{attid}/thumbnail
  summary: Attachment.Api.Attachment.Thumbnail
  parameters:
    path   sensor                   *: integer (int32)  — Sensor id
    path   attid                    *: string  — 
  200: (no body)

### GET /api/v1/sensors/types
  summary: List of all available sensor types.
  200 application/json: ref → sensor.SensorTypeListResponse

### GET /api/v1/sensors/types/type/{sensortype}
  summary: Sensor type metadata.
  parameters:
    path   sensortype               *: string  — Sensor type code
  200 application/json: ref → sensor.SensorTypeResponse
  404 application/json: ref → common.BaseResponse

### GET /api/v1/tags
  summary: All tags
  description: List of all tags.
  200 application/json: ref → tags.TagListResponse

### GET /api/v1/tags/tag/{tag}
  summary: Single tag
  description: Data of a single tag element.
  parameters:
    path   tag                      *: string  — ID of a tag.
  200 application/json: ref → tags.TagResponse

### GET /api/v1/telemetry/history
  summary: Query sensor measurements for period
  description: Novelty value is not relevant for historical measurements
  parameters:
    query  sensor                   : string  — Comma separated sensor serial codes. First 3 sensors by default
    query  metric                   : string  — Filter measurements by comma separated list of metric ids (optional)
    query  unit                     : string  — Express measurements using units given by comma separated list of unit ids. Not valid for application/senml+json
    query  from                     : string (date-time)  — Time period from
    query  to                       : string (date-time)  — Time period to
    query  seconds                  : integer  — Query measurements for last n seconds
    query  minutes                  : integer  — Query measurements for last n minutes
    query  hours                    : integer  — Query measurements for last n hours
    query  days                     : integer  — Query measurements for last n days
    query  next                     : string  — Next page token. Use link from ReadingsListResponse.next or NextLink response header. Due to optimization last page could be empty
    query  limit                    : string  — Rows per page. Due to optimization result page size could be less than limit
    query  links                    : boolean  — Include links to related resources. Enabled by default
  200 application/json: ref → sensor.ReadingsListResponse
  200 application/senml+json: ref → sensor.ReadingsListResponse
  400 application/json: ref → common.BaseResponse
  400 application/senml+json: ref → common.BaseResponse
  500 application/json: ref → common.BaseResponse
  500 application/senml+json: ref → common.BaseResponse

### GET /api/v1/telemetry/last
  summary: Query last telemetry for sensors
  parameters:
    query  sensor                   : string  — Filter telemetry by comma separated list of sensor ids (optional)
    query  metric                   : string  — Filter telemetry by comma separated list of metric ids (optional)
    query  links                    : boolean  — Include links to related resources. Enabled by default
  200 application/json: ref → sensor.ReadingsListResponse
  200 application/senml+json: ref → sensor.ReadingsListResponse
  400 application/json: ref → common.BaseResponse
  400 application/senml+json: ref → common.BaseResponse
  500 application/json: ref → common.BaseResponse
  500 application/senml+json: ref → common.BaseResponse

### GET /api/v1/units/unit/{unit}
  summary: Metrics.Api.UnitRead
  parameters:
    path   unit                     *: string  — 
  200: (no body)
