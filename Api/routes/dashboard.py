"""
Dashboard routes
"""

from flask import render_template
import logging

from Api.utils import (
    get_statistics, get_processing_statistics, get_category_statistics_detailed,
    get_period_comparison, get_recent_files, get_processing_chart_data
)

logger = logging.getLogger(__name__)


def register_dashboard_routes(app):
    """Register dashboard routes with the Flask app"""
    
    @app.route('/')
    def index():
        """Enhanced Dashboard with Real Database Statistics - OPTIMIZED"""
        try:
            stats = get_statistics()
            processing_stats = get_processing_statistics()
            category_stats = get_category_statistics_detailed()
            period_stats = get_period_comparison()
            
            recent_files_list = get_recent_files(limit=10)
            # Convert to format expected by template
            recent_files = [
                {
                    'id': f['id'],
                    'file_name': f['file_name'],
                    'file_type': f['file_type'],
                    'file_status': f['file_status'],
                    'date_creation': f['date_creation'],
                    'file_size': f['file_size'],
                    'file_date': f['file_date'],
                    'source_name': f.get('source_name', 'Unknown'),
                    'side_name': f.get('side_name', 'Unknown')
                }
                for f in recent_files_list
            ]
            
            processing_chart_data = get_processing_chart_data(days=7)
            
            processing_chart = {
                'labels': [str(date) for date, _ in processing_chart_data] if processing_chart_data else [],
                'data': [count for _, count in processing_chart_data] if processing_chart_data else []
            }
            

            percentages = {}
            
            return render_template('Analysis/dashboard.html',
                                 stats=stats,
                                 processing_stats=processing_stats,
                                 category_stats=category_stats,
                                 period_stats=period_stats,
                                 recent_files=recent_files or [],
                                 processing_chart=processing_chart,
                                 percentages=percentages)
            
        except Exception as e:
            logger.error(f"Dashboard error: {e}")
            return render_template('Analysis/dashboard.html',
                                 stats={},
                                 processing_stats={},
                                 category_stats={},
                                 period_stats={},
                                 recent_files=[],
                                 processing_chart={'labels': [], 'data': []},
                                 percentages={})
    
    @app.route('/dashboard/comprehensive')
    def comprehensive_dashboard():
        """Comprehensive Dashboard with multiple layout views"""
        return render_template('Analysis/comprehensive_dashboard.html')
    
    @app.route('/dashboard/charts')
    def charts_dashboard():
        """Charts-only Dashboard with filters - all sections unified"""
        return render_template('Analysis/charts_dashboard.html')

