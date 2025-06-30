import os
from dotenv import load_dotenv
from typing import Dict, List, Optional, Any, Union, Tuple, Callable
from supabase import create_client, Client

load_dotenv()

class SupabaseClient:
    """
    A utility class for interacting with Supabase.
    """
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(SupabaseClient, cls).__new__(cls)
            cls._instance._init_client()
        return cls._instance
    
    def _init_client(self):
        """Initialize the Supabase client using environment variables."""
        # Get Supabase URL and key from environment variables
        supabase_url = os.getenv("SUPABASE_URL")
        supabase_key = os.getenv("SUPABASE_KEY")
        
        if not supabase_url or not supabase_key:
            raise ValueError("SUPABASE_URL and SUPABASE_KEY must be set in the .env file")
        
        self.client: Client = create_client(supabase_url, supabase_key)
    
    def get_client(self) -> Client:
        """Get the raw Supabase client instance."""
        return self.client
    
    # Table operations
    def select(self, table: str, columns: str = "*", filters: Dict = None) -> Dict:
        """
        Select data from a table.
        
        Args:
            table: The table name
            columns: The columns to select (default "*")
            filters: Optional dictionary of filter conditions
            
        Returns:
            The query result
        """
        query = self.client.table(table).select(columns)
        
        if filters:
            for column, value in filters.items():
                query = query.eq(column, value)
                
        return query.execute()
    
    def insert(self, table: str, data: Union[Dict, List[Dict]]) -> Dict:
        """
        Insert data into a table.
        
        Args:
            table: The table name
            data: Data to insert (dict or list of dicts)
            
        Returns:
            The query result
        """
        return self.client.table(table).insert(data).execute()
    
    def update(self, table: str, data: Dict, filters: Dict) -> Dict:
        """
        Update data in a table.
        
        Args:
            table: The table name
            data: Data to update
            filters: Dictionary of filter conditions
            
        Returns:
            The query result
        """
        query = self.client.table(table).update(data)
        
        for column, value in filters.items():
            query = query.eq(column, value)
            
        return query.execute()
    
    def delete(self, table: str, filters: Dict) -> Dict:
        """
        Delete data from a table.
        
        Args:
            table: The table name
            filters: Dictionary of filter conditions
            
        Returns:
            The query result
        """
        query = self.client.table(table).delete()
        
        for column, value in filters.items():
            query = query.eq(column, value)
            
        return query.execute()
    
    def upsert(self, table: str, data: Union[Dict, List[Dict]]) -> Dict:
        """
        Upsert data (insert or update if exists).
        
        Args:
            table: The table name
            data: Data to upsert
            
        Returns:
            The query result
        """
        return self.client.table(table).upsert(data).execute()
        
    def insert_with_tracking(self, 
                            table_name: str, 
                            data: List[Dict[str, Any]], 
                            filter_field: Optional[str] = None, 
                            filter_value: Optional[str] = None,
                            log_callback: Optional[Callable[[str], None]] = print) -> Tuple[int, int]:
        """
        Enhanced insert function that tracks success/failure and provides detailed logging.
        
        Args:
            table_name: The name of the table to insert data into
            data: List of dictionaries containing the data to insert
            filter_field: Optional field name to use for verification
            filter_value: Optional field value to use for verification
            log_callback: Function to call with log messages (default: print)
            
        Returns:
            Tuple[int, int]: (success_count, error_count)
        """
        if log_callback:
            log_callback(f"Preparing to insert {len(data)} records into {table_name} table...")
        
        success_count = 0
        error_count = 0
        
        # Ensure data is a list for consistent handling
        data_to_insert = data if isinstance(data, list) else [data]
        
        for i, record in enumerate(data_to_insert):
            try:
                # Insert the record into the specified table
                result = self.client.table(table_name).insert(record).execute()
                
                # Check if the insert was successful
                if result.data:
                    record_type = record.get('task_type', 'Record') if 'task_type' in record else 'Record'
                    record_id = record.get('task_id', record.get('id', i+1)) if 'task_id' in record or 'id' in record else i+1
                    if log_callback:
                        log_callback(f"✅ Successfully inserted {record_type} {i+1}/{len(data_to_insert)}: (ID: {record_id})")
                    success_count += 1
                else:
                    if log_callback:
                        log_callback(f"❌ Failed to insert record {i+1}/{len(data_to_insert)}")
                        if hasattr(result, 'error'):
                            log_callback(f"   Error: {result.error}")
                    error_count += 1
            
            except Exception as e:
                if log_callback:
                    log_callback(f"❌ Error inserting record {i+1}/{len(data_to_insert)}: {str(e)}")
                error_count += 1
        
        if log_callback:
            log_callback(f"\nInsertion complete! Successful: {success_count}, Failed: {error_count}")
        
        # Verify the inserted data if requested
        if filter_field and filter_value:
            self.verify_insertion(table_name, filter_field, filter_value, log_callback)
        
        return success_count, error_count
    
    def verify_insertion(self, 
                         table_name: str, 
                         filter_field: str, 
                         filter_value: str,
                         log_callback: Optional[Callable[[str], None]] = print) -> int:
        """
        Verify that data was inserted by querying the specified table
        
        Args:
            table_name: The name of the table to query
            filter_field: The field name to filter on 
            filter_value: The value to filter for
            log_callback: Function to call with log messages (default: print)
            
        Returns:
            int: Number of records found
        """
        try:
            # Query for records matching the filter
            result = self.client.table(table_name).select("*").eq(filter_field, filter_value).execute()
            
            if result.data:
                if log_callback:
                    log_callback(f"\nVerification: Found {len(result.data)} records in the {table_name} table where {filter_field}='{filter_value}'.")
                return len(result.data)
            else:
                if log_callback:
                    log_callback(f"\nVerification: No records found in the {table_name} table where {filter_field}='{filter_value}'.")
                return 0
            
        except Exception as e:
            if log_callback:
                log_callback(f"\nError verifying data: {str(e)}")
            return -1

# Create a singleton instance
supabase = SupabaseClient()