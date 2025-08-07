"""
API error tracking and notifications module.

This module provides functionality to track API errors and generate
alerts when error rates exceed predefined thresholds.

Created: 2025-08-05
"""

import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict, Counter
import json
import traceback

from .base import MonitoringService, MonitoringAlert, AlertSeverity, AlertType, AlertStatus
from .models import ApiErrorData, ApiErrorType, ApiErrorSeverity
from ..database import Database
from ..logger import Logger
from ..notifications import NotificationHandler
from ..models import Coin, Pair
from ..binance_api_manager import BinanceAPIManager


class ApiErrorTracker(MonitoringService):
    """
    Service for tracking API errors and generating alerts.
    
    This service monitors API error rates, response times, and
    generates alerts when error rates exceed predefined thresholds.
    """
    
    def __init__(
        self,
        database: Database,
        logger: Logger,
        notifications: NotificationHandler,
        config: Dict[str, Any],
        binance_manager: BinanceAPIManager
    ):
        """
        Initialize the API error tracker.
        
        @description Create a new API error tracker instance
        @param {Database} database - Database connection for data storage
        @param {Logger} logger - Logger instance for logging
        @param {NotificationHandler} notifications - Notification handler for alerts
        @param {Dict} config - Configuration dictionary for API error tracking settings
        @param {BinanceAPIManager} binance_manager - Binance API manager for data retrieval
        @returns {ApiErrorTracker} New API error tracker instance
        """
        super().__init__(database, logger, notifications, config)
        
        self.binance_manager = binance_manager
        
        # Configuration settings
        self.error_thresholds = config.get('error_thresholds', {
            'error_rate_per_hour': {
                'low': 0.05,    # 5%
                'medium': 0.10, # 10%
                'high': 0.20,   # 20%
                'critical': 0.30 # 30%
            },
            'response_time_thresholds': {
                'slow': 1000,   # 1 second
                'very_slow': 3000,  # 3 seconds
                'extremely_slow': 10000  # 10 seconds
            },
            'consecutive_errors': {
                'low': 3,
                'medium': 5,
                'high': 10,
                'critical': 20
            },
            'error_types': {
                'rate_limit': {
                    'severity': ApiErrorSeverity.WARNING.value,
                    'threshold': 5
                },
                'connection_error': {
                    'severity': ApiErrorSeverity.ERROR.value,
                    'threshold': 3
                },
                'authentication_error': {
                    'severity': ApiErrorSeverity.CRITICAL.value,
                    'threshold': 1
                },
                'server_error': {
                    'severity': ApiErrorSeverity.ERROR.value,
                    'threshold': 5
                },
                'timeout_error': {
                    'severity': ApiErrorSeverity.WARNING.value,
                    'threshold': 10
                }
            }
        })
        
        self.monitoring_periods = config.get('monitoring_periods', {
            ApiErrorType.RATE_LIMIT.value: 60,      # 1 hour
            ApiErrorType.CONNECTION_ERROR.value: 60,  # 1 hour
            ApiErrorType.AUTHENTICATION_ERROR.value: 60,  # 1 hour
            ApiErrorType.SERVER_ERROR.value: 60,    # 1 hour
            ApiErrorType.TIMEOUT_ERROR.value: 60,    # 1 hour
            ApiErrorType.UNKNOWN_ERROR.value: 60     # 1 hour
        })
        
        self.endpoints_to_monitor = config.get('endpoints_to_monitor', [
            'get_ticker_price',
            'get_klines',
            'get_currency_balance',
            'get_fee',
            'get_min_notional',
            'sell_alt',
            'buy_alt'
        ])
        
        # Alert cooldown settings
        self.alert_cooldown_period = config.get('alert_cooldown_period', 30)  # 30 minutes
        self.last_alerts: Dict[str, datetime] = {}  # endpoint_error_type -> last alert time
        
        # Cache for recent API calls
        self.recent_api_calls: List[Dict[str, Any]] = []
        self.last_api_sync = datetime.utcnow()
        
        # Hook into binance manager to track API calls
        self._setup_api_hooks()
        
    def _setup_api_hooks(self):
        """
        Setup hooks to track API calls.
        
        @description Install hooks to monitor API calls made by the binance manager
        @returns {void}
        """
        try:
            # Store original methods
            self.original_methods = {}
            
            # Methods to hook
            methods_to_hook = [
                'get_ticker_price',
                'get_klines',
                'get_currency_balance',
                'get_fee',
                'get_min_notional',
                'sell_alt',
                'buy_alt'
            ]
            
            for method_name in methods_to_hook:
                if hasattr(self.binance_manager, method_name):
                    original_method = getattr(self.binance_manager, method_name)
                    self.original_methods[method_name] = original_method
                    
                    # Create wrapped method
                    wrapped_method = self._create_wrapped_method(method_name, original_method)
                    setattr(self.binance_manager, method_name, wrapped_method)
                    
        except Exception as e:
            self.logger.error(f"Error setting up API hooks: {e}")
            
    def _create_wrapped_method(self, method_name: str, original_method):
        """
        Create a wrapped method to track API calls.
        
        @description Create a wrapper method to monitor API calls
        @param {str} method_name - Name of the method to wrap
        @param {function} original_method - Original method to wrap
        @returns {function} Wrapped method with tracking
        """
        async def wrapped_method(*args, **kwargs):
            start_time = datetime.utcnow()
            success = False
            error_type = None
            error_message = None
            response_time = None
            
            try:
                result = await original_method(*args, **kwargs)
                success = True
                return result
                
            except Exception as e:
                # Determine error type
                error_type = self._classify_error(e)
                error_message = str(e)
                
                # Log the error
                self.logger.error(f"API Error in {method_name}: {error_type} - {error_message}")
                
                # Create API error record
                api_error = {
                    'timestamp': start_time,
                    'method': method_name,
                    'success': False,
                    'error_type': error_type,
                    'error_message': error_message,
                    'response_time': None,
                    'args': str(args)[:100],  # Truncate for storage
                    'kwargs': str(kwargs)[:100]  # Truncate for storage
                }
                
                # Add to recent API calls
                self.recent_api_calls.append(api_error)
                
                # Keep only last 1000 calls
                if len(self.recent_api_calls) > 1000:
                    self.recent_api_calls = self.recent_api_calls[-1000:]
                
                raise
                
            finally:
                # Calculate response time
                end_time = datetime.utcnow()
                response_time = (end_time - start_time).total_seconds() * 1000  # in milliseconds
                
                # Create success record
                if success:
                    api_call = {
                        'timestamp': start_time,
                        'method': method_name,
                        'success': True,
                        'error_type': None,
                        'error_message': None,
                        'response_time': response_time,
                        'args': str(args)[:100],  # Truncate for storage
                        'kwargs': str(kwargs)[:100]  # Truncate for storage
                    }
                    
                    # Add to recent API calls
                    self.recent_api_calls.append(api_call)
                    
                    # Keep only last 1000 calls
                    if len(self.recent_api_calls) > 1000:
                        self.recent_api_calls = self.recent_api_calls[-1000:]
        
        return wrapped_method
        
    def _classify_error(self, error: Exception) -> ApiErrorType:
        """
        Classify API error type.
        
        @description Determine the type of API error based on exception
        @param {Exception} error - Exception to classify
        @returns {ApiErrorType} Classified error type
        """
        error_message = str(error).lower()
        
        if 'rate limit' in error_message or 'too many requests' in error_message:
            return ApiErrorType.RATE_LIMIT
        elif 'connection' in error_message or 'network' in error_message:
            return ApiErrorType.CONNECTION_ERROR
        elif 'authentication' in error_message or 'api key' in error_message or 'signature' in error_message:
            return ApiErrorType.AUTHENTICATION_ERROR
        elif 'server' in error_message or 'internal' in error_message or '500' in error_message:
            return ApiErrorType.SERVER_ERROR
        elif 'timeout' in error_message or 'read timeout' in error_message:
            return ApiErrorType.TIMEOUT_ERROR
        else:
            return ApiErrorType.UNKNOWN_ERROR
            
    async def collect_data(self) -> Dict[str, Any]:
        """
        Collect API error data.
        
        @description Collect recent API call data for error analysis
        @returns {Dict} Dictionary containing collected API error data
        """
        self.logger.info("Starting API error data collection")
        
        data = {
            'api_calls': [],
            'endpoints': {},
            'timestamp': datetime.utcnow()
        }
        
        try:
            # Sync recent API calls
            await self._sync_api_calls()
            
            # Add API calls to data
            data['api_calls'] = self.recent_api_calls
            
            # Collect endpoint data
            for endpoint in self.endpoints_to_monitor:
                endpoint_data = await self._collect_endpoint_data(endpoint)
                if endpoint_data:
                    data['endpoints'][endpoint] = endpoint_data
            
            self.logger.info(f"Collected API data for {len(data['api_calls'])} calls and {len(data['endpoints'])} endpoints")
            return data
            
        except Exception as e:
            self.logger.error(f"Error collecting API error data: {e}")
            raise
            
    async def _sync_api_calls(self):
        """
        Sync recent API calls from cache.
        
        @description Sync API calls from internal cache
        @returns {void}
        """
        try:
            # API calls are already stored in self.recent_api_calls
            # Just ensure we have recent data
            cutoff_time = datetime.utcnow() - timedelta(hours=1)
            
            # Filter calls from the last hour
            self.recent_api_calls = [
                call for call in self.recent_api_calls
                if call['timestamp'] >= cutoff_time
            ]
            
        except Exception as e:
            self.logger.error(f"Error syncing API calls: {e}")
            self.recent_api_calls = []
            
    async def _collect_endpoint_data(self, endpoint: str) -> Optional[Dict[str, Any]]:
        """
        Collect API error data for a specific endpoint.
        
        @description Collect API error data for a single endpoint
        @param {str} endpoint - Name of the endpoint to collect data for
        @returns {Dict|null} Dictionary containing API error data or None if failed
        """
        try:
            # Filter calls for this endpoint
            endpoint_calls = [
                call for call in self.recent_api_calls
                if call['method'] == endpoint
            ]
            
            if not endpoint_calls:
                return None
            
            # Calculate error metrics
            total_calls = len(endpoint_calls)
            successful_calls = len([c for c in endpoint_calls if c['success']])
            failed_calls = total_calls - successful_calls
            
            # Group errors by type
            error_counts = Counter([c['error_type'] for c in endpoint_calls if not c['success']])
            
            # Calculate response time statistics
            response_times = [c['response_time'] for c in endpoint_calls if c['response_time'] is not None]
            
            endpoint_data = {
                'total_calls': total_calls,
                'successful_calls': successful_calls,
                'failed_calls': failed_calls,
                'error_rate': failed_calls / total_calls if total_calls > 0 else 0,
                'error_counts': dict(error_counts),
                'avg_response_time': sum(response_times) / len(response_times) if response_times else 0,
                'max_response_time': max(response_times) if response_times else 0,
                'min_response_time': min(response_times) if response_times else 0,
                'calls_by_hour': self._group_calls_by_period(endpoint_calls, 'hour'),
                'calls_by_minute': self._group_calls_by_period(endpoint_calls, 'minute')
            }
            
            return endpoint_data
            
        except Exception as e:
            self.logger.error(f"Error collecting API error data for endpoint {endpoint}: {e}")
            return None
            
    def _group_calls_by_period(self, calls: List[Dict[str, Any]], period: str) -> Dict[str, int]:
        """
        Group API calls by time period.
        
        @description Group API calls by hour or minute for frequency analysis
        @param {List} calls - List of API calls to group
        @param {str} period - Time period ('hour' or 'minute')
        @returns {Dict} Dictionary with period keys and call counts
        """
        if not calls:
            return {}
        
        try:
            grouped = defaultdict(int)
            
            for call in calls:
                timestamp = call['timestamp']
                
                if period == 'hour':
                    key = timestamp.strftime('%Y-%m-%d %H:00')
                elif period == 'minute':
                    key = timestamp.strftime('%Y-%m-%d %H:%M')
                else:
                    continue
                
                grouped[key] += 1
            
            return dict(grouped)
            
        except Exception as e:
            self.logger.error(f"Error grouping API calls by period: {e}")
            return {}
            
    async def analyze_data(self, data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze collected API error data and detect unusual error patterns.
        
        @description Analyze API error data to identify unusual error patterns
        @param {Dict} data - Collected API error data
        @returns {List} List of API error alerts
        """
        self.logger.info("Starting API error analysis")
        
        alerts = []
        
        try:
            # Analyze endpoint data
            for endpoint, endpoint_data in data.get('endpoints', {}).items():
                endpoint_alerts = await self._analyze_endpoint_errors(endpoint, endpoint_data)
                alerts.extend(endpoint_alerts)
            
            # Analyze global error patterns
            global_alerts = await self._analyze_global_error_patterns(data.get('api_calls', []))
            alerts.extend(global_alerts)
            
            self.logger.info(f"Generated {len(alerts)} API error alerts")
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing API error data: {e}")
            return []
            
    async def _analyze_endpoint_errors(self, endpoint: str, endpoint_data: Dict[str, Any]) -> List[MonitoringAlert]:
        """
        Analyze API errors for a specific endpoint.
        
        @description Analyze error patterns for a single API endpoint
        @param {str} endpoint - Name of the endpoint
        @param {Dict} endpoint_data - API error data for the endpoint
        @returns {List} List of API error alerts for the endpoint
        """
        alerts = []
        
        try:
            # Analyze error rate
            error_rate_alert = await self._analyze_error_rate_frequency(
                endpoint=endpoint,
                endpoint_data=endpoint_data
            )
            
            # Analyze response time
            response_time_alert = await self._analyze_response_time_frequency(
                endpoint=endpoint,
                endpoint_data=endpoint_data
            )
            
            # Analyze consecutive errors
            consecutive_errors_alert = await self._analyze_consecutive_errors_frequency(
                endpoint=endpoint,
                endpoint_data=endpoint_data
            )
            
            # Analyze specific error types
            error_type_alerts = await self._analyze_error_type_frequency(
                endpoint=endpoint,
                endpoint_data=endpoint_data
            )
            
            # Add alerts if they exist
            for alert in [error_rate_alert, response_time_alert, consecutive_errors_alert] + error_type_alerts:
                if alert:
                    alerts.append(alert)
                    
                    # Store API error data in database
                    await self._store_api_error_data(
                        endpoint=endpoint,
                        alert=alert,
                        endpoint_data=endpoint_data
                    )
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing API errors for endpoint {endpoint}: {e}")
            return []
            
    async def _analyze_global_error_patterns(self, api_calls: List[Dict[str, Any]]) -> List[MonitoringAlert]:
        """
        Analyze global API error patterns across all endpoints.
        
        @description Analyze error patterns across all API endpoints
        @param {List} api_calls - List of API calls to analyze
        @returns {List} List of global API error alerts
        """
        alerts = []
        
        try:
            # Calculate global error rate
            total_calls = len(api_calls)
            failed_calls = len([c for c in api_calls if not c['success']])
            global_error_rate = failed_calls / total_calls if total_calls > 0 else 0
            
            # Check against global error rate thresholds
            severity = self._determine_error_rate_severity(
                global_error_rate,
                self.error_thresholds['error_rate_per_hour']
            )
            
            if severity:
                # Create alert
                alert = MonitoringAlert(
                    alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                    severity=severity,
                    title="High Global API Error Rate",
                    description=(
                        f"Unusually high global API error rate detected.\n\n"
                        f"Global Error Rate: {global_error_rate:.2%}\n"
                        f"Total Calls: {total_calls}\n"
                        f"Failed Calls: {failed_calls}\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    threshold_value=self.error_thresholds['error_rate_per_hour'][severity.value.lower()],
                    current_value=global_error_rate,
                    metadata={
                        'metric_type': 'global_error_rate',
                        'total_calls': total_calls,
                        'failed_calls': failed_calls,
                        'successful_calls': total_calls - failed_calls
                    },
                    context={
                        'analysis_timestamp': datetime.utcnow().isoformat(),
                        'global_error_rate': global_error_rate
                    }
                )
                
                alerts.append(alert)
                
                # Store global error data
                await self._store_global_error_data(alert, api_calls)
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing global error patterns: {e}")
            return []
            
    async def _analyze_error_rate_frequency(
        self,
        endpoint: str,
        endpoint_data: Dict[str, Any]
    ) -> Optional[MonitoringAlert]:
        """
        Analyze error rate frequency for an endpoint.
        
        @description Analyze error rate to identify unusual error patterns
        @param {str} endpoint - Name of the endpoint
        @param {Dict} endpoint_data - API error data for the endpoint
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            error_rate = endpoint_data.get('error_rate', 0)
            
            # Check against thresholds
            severity = self._determine_error_rate_severity(
                error_rate,
                self.error_thresholds['error_rate_per_hour']
            )
            
            if severity:
                # Check cooldown period
                identifier = f"{endpoint}_error_rate"
                
                if identifier in self.last_alerts:
                    time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                    if time_since_last < self.alert_cooldown_period:
                        return None
                
                # Create alert
                alert = MonitoringAlert(
                    alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                    severity=severity,
                    title=f"High Error Rate Alert: {endpoint}",
                    description=(
                        f"Unusually high error rate detected for {endpoint} API endpoint.\n\n"
                        f"Error Rate: {error_rate:.2%}\n"
                        f"Total Calls: {endpoint_data.get('total_calls', 0)}\n"
                        f"Failed Calls: {endpoint_data.get('failed_calls', 0)}\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    threshold_value=self.error_thresholds['error_rate_per_hour'][severity.value.lower()],
                    current_value=error_rate,
                    metadata={
                        'metric_type': 'endpoint_error_rate',
                        'endpoint': endpoint,
                        'total_calls': endpoint_data.get('total_calls', 0),
                        'failed_calls': endpoint_data.get('failed_calls', 0),
                        'successful_calls': endpoint_data.get('successful_calls', 0)
                    },
                    context={
                        'endpoint': endpoint,
                        'analysis_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Update last alert time
                self.last_alerts[identifier] = datetime.utcnow()
                
                return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing error rate frequency: {e}")
            return None
            
    async def _analyze_response_time_frequency(
        self,
        endpoint: str,
        endpoint_data: Dict[str, Any]
    ) -> Optional[MonitoringAlert]:
        """
        Analyze response time frequency for an endpoint.
        
        @description Analyze response time to identify unusual performance patterns
        @param {str} endpoint - Name of the endpoint
        @param {Dict} endpoint_data - API error data for the endpoint
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            max_response_time = endpoint_data.get('max_response_time', 0)
            avg_response_time = endpoint_data.get('avg_response_time', 0)
            
            # Check against response time thresholds
            severity = self._determine_response_time_severity(max_response_time)
            
            if severity:
                # Check cooldown period
                identifier = f"{endpoint}_response_time"
                
                if identifier in self.last_alerts:
                    time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                    if time_since_last < self.alert_cooldown_period:
                        return None
                
                # Create alert
                alert = MonitoringAlert(
                    alert_type=AlertType.API_PERFORMANCE_DEGRADED,
                    severity=severity,
                    title=f"Slow Response Time Alert: {endpoint}",
                    description=(
                        f"Unusually slow response time detected for {endpoint} API endpoint.\n\n"
                        f"Max Response Time: {max_response_time:.0f}ms\n"
                        f"Average Response Time: {avg_response_time:.0f}ms\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    threshold_value=self.error_thresholds['response_time_thresholds'][severity.value.lower()],
                    current_value=max_response_time,
                    metadata={
                        'metric_type': 'endpoint_response_time',
                        'endpoint': endpoint,
                        'max_response_time': max_response_time,
                        'avg_response_time': avg_response_time,
                        'min_response_time': endpoint_data.get('min_response_time', 0)
                    },
                    context={
                        'endpoint': endpoint,
                        'analysis_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Update last alert time
                self.last_alerts[identifier] = datetime.utcnow()
                
                return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing response time frequency: {e}")
            return None
            
    async def _analyze_consecutive_errors_frequency(
        self,
        endpoint: str,
        endpoint_data: Dict[str, Any]
    ) -> Optional[MonitoringAlert]:
        """
        Analyze consecutive errors frequency for an endpoint.
        
        @description Analyze consecutive errors to identify unusual error patterns
        @param {str} endpoint - Name of the endpoint
        @param {Dict} endpoint_data - API error data for the endpoint
        @returns {MonitoringAlert|null} Alert object or None if no threshold exceeded
        """
        try:
            # Get recent calls for this endpoint
            endpoint_calls = [
                call for call in self.recent_api_calls
                if call['method'] == endpoint
            ]
            
            if not endpoint_calls:
                return None
            
            # Calculate consecutive errors
            consecutive_errors = self._calculate_consecutive_errors(endpoint_calls)
            
            # Check against thresholds
            severity = self._determine_consecutive_errors_severity(consecutive_errors)
            
            if severity:
                # Check cooldown period
                identifier = f"{endpoint}_consecutive_errors"
                
                if identifier in self.last_alerts:
                    time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                    if time_since_last < self.alert_cooldown_period:
                        return None
                
                # Create alert
                alert = MonitoringAlert(
                    alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                    severity=severity,
                    title=f"High Consecutive Errors Alert: {endpoint}",
                    description=(
                        f"Unusually high number of consecutive errors detected for {endpoint} API endpoint.\n\n"
                        f"Consecutive Errors: {consecutive_errors}\n"
                        f"Analysis period: Last hour\n"
                        f"Threshold exceeded: {severity.value} severity"
                    ),
                    threshold_value=self.error_thresholds['consecutive_errors'][severity.value.lower()],
                    current_value=consecutive_errors,
                    metadata={
                        'metric_type': 'endpoint_consecutive_errors',
                        'endpoint': endpoint,
                        'consecutive_errors': consecutive_errors
                    },
                    context={
                        'endpoint': endpoint,
                        'analysis_timestamp': datetime.utcnow().isoformat()
                    }
                )
                
                # Update last alert time
                self.last_alerts[identifier] = datetime.utcnow()
                
                return alert
            
            return None
            
        except Exception as e:
            self.logger.error(f"Error analyzing consecutive errors frequency: {e}")
            return None
            
    async def _analyze_error_type_frequency(
        self,
        endpoint: str,
        endpoint_data: Dict[str, Any]
    ) -> List[MonitoringAlert]:
        """
        Analyze error type frequency for an endpoint.
        
        @description Analyze specific error types to identify unusual patterns
        @param {str} endpoint - Name of the endpoint
        @param {Dict} endpoint_data - API error data for the endpoint
        @returns {List} List of error type alerts
        """
        alerts = []
        
        try:
            error_counts = endpoint_data.get('error_counts', {})
            
            for error_type, count in error_counts.items():
                # Get error type configuration
                error_config = self.error_thresholds['error_types'].get(error_type.value, {})
                if not error_config:
                    continue
                
                threshold = error_config.get('threshold', 0)
                severity = AlertSeverity(error_config.get('severity', AlertSeverity.MEDIUM.value))
                
                if count >= threshold:
                    # Check cooldown period
                    identifier = f"{endpoint}_{error_type.value}"
                    
                    if identifier in self.last_alerts:
                        time_since_last = (datetime.utcnow() - self.last_alerts[identifier]).total_seconds() / 60
                        if time_since_last < self.alert_cooldown_period:
                            continue
                    
                    # Create alert
                    alert = MonitoringAlert(
                        alert_type=AlertType.API_ERROR_RATE_EXCEEDED,
                        severity=severity,
                        title=f"High {error_type.value.replace('_', ' ').title()} Alert: {endpoint}",
                        description=(
                            f"Unusually high number of {error_type.value.replace('_', ' ')} errors detected for {endpoint} API endpoint.\n\n"
                            f"Error Type: {error_type.value.replace('_', ' ').title()}\n"
                            f"Error Count: {count}\n"
                            f"Threshold: {threshold}\n"
                            f"Severity: {severity.value}"
                        ),
                        threshold_value=threshold,
                        current_value=count,
                        metadata={
                            'metric_type': 'endpoint_error_type',
                            'endpoint': endpoint,
                            'error_type': error_type.value,
                            'error_count': count
                        },
                        context={
                            'endpoint': endpoint,
                            'error_type': error_type.value,
                            'analysis_timestamp': datetime.utcnow().isoformat()
                        }
                    )
                    
                    alerts.append(alert)
                    
                    # Update last alert time
                    self.last_alerts[identifier] = datetime.utcnow()
            
            return alerts
            
        except Exception as e:
            self.logger.error(f"Error analyzing error type frequency: {e}")
            return []
            
    def _calculate_consecutive_errors(self, calls: List[Dict[str, Any]]) -> int:
        """
        Calculate maximum number of consecutive errors.
        
        @description Calculate the maximum number of consecutive errors for an endpoint
        @param {List} calls - List of API calls to analyze
        @returns {int} Maximum number of consecutive errors
        """
        if not calls:
            return 0
        
        try:
            # Sort calls by timestamp
            sorted_calls = sorted(calls, key=lambda x: x['timestamp'])
            
            max_consecutive = 0
            current_consecutive = 0
            
            for call in sorted_calls:
                if not call['success']:
                    current_consecutive += 1
                    max_consecutive = max(max_consecutive, current_consecutive)
                else:
                    current_consecutive = 0
            
            return max_consecutive
            
        except Exception as e:
            self.logger.error(f"Error calculating consecutive errors: {e}")
            return 0
            
    def _determine_error_rate_severity(self, error_rate: float, thresholds: Dict[str, float]) -> Optional[AlertSeverity]:
        """
        Determine alert severity based on error rate.
        
        @description Calculate alert severity based on error rate thresholds
        @param {float} error_rate - Error rate to evaluate
        @param {Dict} thresholds - Threshold dictionary with severity levels
        @returns {AlertSeverity|null} Determined severity level or None if no threshold exceeded
        """
        if error_rate >= thresholds['critical']:
            return AlertSeverity.CRITICAL
        elif error_rate >= thresholds['high']:
            return AlertSeverity.HIGH
        elif error_rate >= thresholds['medium']:
            return AlertSeverity.MEDIUM
        elif error_rate >= thresholds['low']:
            return AlertSeverity.LOW
        else:
            return None
            
    def _determine_response_time_severity(self, response_time: float) -> Optional[AlertSeverity]:
        """
        Determine alert severity based on response time.
        
        @description Calculate alert severity based on response time thresholds
        @param {float} response_time - Response time in milliseconds
        @returns {AlertSeverity|null} Determined severity level or None if no threshold exceeded
        """
        if response_time >= self.error_thresholds['response_time_thresholds']['extremely_slow']:
            return AlertSeverity.CRITICAL
        elif response_time >= self.error_thresholds['response_time_thresholds']['very_slow']:
            return AlertSeverity.HIGH
        elif response_time >= self.error_thresholds['response_time_thresholds']['slow']:
            return AlertSeverity.MEDIUM
        else:
            return None
            
    def _determine_consecutive_errors_severity(self, consecutive_errors: int) -> Optional[AlertSeverity]:
        """
        Determine alert severity based on consecutive errors.
        
        @description Calculate alert severity based on consecutive error thresholds
        @param {int} consecutive_errors - Number of consecutive errors
        @returns {AlertSeverity|null} Determined severity level or None if no threshold exceeded
        """
        if consecutive_errors >= self.error_thresholds['consecutive_errors']['critical']:
            return AlertSeverity.CRITICAL
        elif consecutive_errors >= self.error_thresholds['consecutive_errors']['high']:
            return AlertSeverity.HIGH
        elif consecutive_errors >= self.error_thresholds['consecutive_errors']['medium']:
            return AlertSeverity.MEDIUM
        elif consecutive_errors >= self.error_thresholds['consecutive_errors']['low']:
            return AlertSeverity.LOW
        else:
            return None
            
    async def _store_api_error_data(
        self,
        endpoint: str,
        alert: MonitoringAlert,
        endpoint_data: Dict[str, Any]
    ):
        """
        Store API error data in the database.
        
        @description Store API error measurement in database for historical tracking
        @param {str} endpoint - API endpoint name
        @param {MonitoringAlert} alert - Alert containing error information
        @param {Dict} endpoint_data - API error data for the endpoint
        @returns {void}
        """
        try:
            # Convert string metric type to enum
            metric_type_str = alert.metadata.get('metric_type', 'unknown')
            metric_enum = ApiErrorType(metric_type_str) if hasattr(ApiErrorType, metric_type_str) else ApiErrorType.UNKNOWN_ERROR
            
            # Create API error data record
            error_data = ApiErrorData(
                endpoint=endpoint,
                error_type=metric_enum,
                period=self.monitoring_periods.get(metric_enum, 60),
                error_value=alert.current_value,
                threshold_value=alert.threshold_value,
                metadata={
                    'alert_id': alert.alert_uuid,
                    'total_calls': endpoint_data.get('total_calls', 0),
                    'successful_calls': endpoint_data.get('successful_calls', 0),
                    'failed_calls': endpoint_data.get('failed_calls', 0),
                    'monitoring_timestamp': datetime.utcnow().isoformat(),
                    'tracker_version': '1.0.0'
                }
            )
            
            # Store in database
            session = self.database.db_session()
            session.add(error_data)
            session.commit()
            
        except Exception as e:
            self.logger.error(f"Error storing API error data: {e}")
            
    async def _store_global_error_data(
        self,
        alert: MonitoringAlert,
        api_calls: List[Dict[str, Any]]
    ):
        """
        Store global API error data in the database.
        
        @description Store global API error measurement in database for historical tracking
        @param {MonitoringAlert} alert - Alert containing global error information
        @param {List} api_calls - List of API calls analyzed
        @returns {void}
        """
        try:
            # Create API error data record
            error_data = ApiErrorData(
                endpoint='global',
                error_type=ApiErrorType.UNKNOWN_ERROR,
                period=60,  # 1 hour
                error_value=alert.current_value,
                threshold_value=alert.threshold_value,
                metadata={
                    'alert_id': alert.alert_uuid,
                    'total_calls': len(api_calls),
                    'successful_calls': alert.metadata.get('successful_calls', 0),
                    'failed_calls': alert.metadata.get('failed_calls', 0),
                    'monitoring_timestamp': datetime.utcnow().isoformat(),
                    'tracker_version': '1.0.0'
                }
            )
            
            # Store in database
            session = self.database.db_session()
            session.add(error_data)
            session.commit()
            
        except Exception as e:
            self.logger.error(f"Error storing global API error data: {e}")
            
    async def generate_report(self, alerts: List[MonitoringAlert]) -> str:
        """
        Generate an API error tracking report.
        
        @description Generate a human-readable report of API error tracking findings
        @param {List} alerts - List of alerts to include in the report
        @returns {str} Generated report text
        """
        if not alerts:
            return "✅ No API error alerts generated. API performance appears normal."
        
        report_lines = [
            "🔌 API Error Tracking Report",
            "=" * 50,
            f"Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Total Alerts: {len(alerts)}",
            ""
        ]
        
        # Group alerts by severity
        alerts_by_severity = {}
        for alert in alerts:
            severity = alert.severity.value
            if severity not in alerts_by_severity:
                alerts_by_severity[severity] = []
            alerts_by_severity[severity].append(alert)
        
        # Report by severity
        severity_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']
        for severity in severity_order:
            if severity in alerts_by_severity:
                report_lines.append(f"🚨 {severity} Severity Alerts: {len(alerts_by_severity[severity])}")
                
                for alert in alerts_by_severity[severity][:3]:  # Show top 3 per severity
                    endpoint = alert.metadata.get('endpoint', 'global')
                    metric_type = alert.metadata.get('metric_type', 'Unknown')
                    current_value = alert.current_value
                    
                    report_lines.append(f"  • {alert.title}")
                    report_lines.append(f"    Endpoint: {endpoint}")
                    report_lines.append(f"    Metric: {metric_type}")
                    report_lines.append(f"    Current Value: {current_value}")
                
                if len(alerts_by_severity[severity]) > 3:
                    report_lines.append(f"  ... and {len(alerts_by_severity[severity]) - 3} more")
                
                report_lines.append("")
        
        # Summary statistics
        report_lines.append("📊 Summary Statistics:")
        report_lines.append(f"• Endpoints monitored: {len(self.endpoints_to_monitor)}")
        report_lines.append(f"• Alert cooldown: {self.alert_cooldown_period} minutes")
        report_lines.append(f"• Recent API calls analyzed: {len(self.recent_api_calls)}")
        
        return "\n".join(report_lines)